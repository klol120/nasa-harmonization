# Position encoding/interpolation adapted from IBM Corp. 2024, Apache-2.0.
# Modified CPU-only encoder adapter; see docs/pretrained-sources.md.
"""Strict CPU encoder adapter for published IBM/NASA Prithvi checkpoints.

Position encoding/interpolation follows IBM's Apache-2.0 prithvi_mae.py; see
docs/pretrained-sources.md for pinned sources and attribution. Decoder weights are
not used. Checkpoint loading uses torch weights_only=True, never remote code.
"""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlencode

import numpy as np


def hls_clear_pixels(quality):
    q = np.asarray(quality, dtype=np.uint8)
    return (q != 255) & ((q & 63) == 0) & ((q >> 6) < 3)


def discover(root, config_path):
    from datetime import datetime, timezone
    folder = Path(root) / 'data/pretrained-models'
    folder.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(config_path).read_text())
    for record in config['models']:
        target = folder / record['repository'].split('/')[-1]
        target.mkdir(exist_ok=True)
        for name in ['config.json', 'prithvi_mae.py', 'README.md']:
            path = target / name
            url = 'https://huggingface.co/' + record['repository'] + '/resolve/' + record['revision'] + '/' + name
            with urllib.request.urlopen(url, timeout=45) as response:
                raw = response.read(100000)
            if path.exists() and path.read_bytes() != raw:
                raise ValueError('Pinned upstream source differs from cached file')
            path.write_bytes(raw)
            path.with_suffix(path.suffix + '.manifest.json').write_text(json.dumps({
                'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}, indent=2))
    catalog = folder / 'hls-catalog.json'
    if not catalog.exists():
        params = {'short_name': 'HLSL30', 'version': '2.0', 'bounding_box': '35,33,36.7,34.75',
                  'temporal': '2017-06-01T00:00:00Z,2017-10-31T23:59:59Z', 'page_size': 200, 'sort_key': 'start_date'}
        url = 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        if len(json.loads(raw)['feed']['entry']) >= 200:
            raise ValueError('HLS inventory may be truncated; implement pagination before expansion')
        catalog.write_bytes(raw)
        catalog.with_suffix('.json.manifest.json').write_text(json.dumps({
            'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}, indent=2))
    print('Pinned model metadata and NASA HLS catalogue ready', flush=True)


def sincos(width, positions):
    positions = np.asarray(positions).reshape(-1)
    omega = 10000. ** (-np.arange(width // 2, dtype=float) / (width / 2))
    phases = np.outer(positions, omega)
    return np.concatenate([np.sin(phases), np.cos(phases)], axis=1)


def position_encoding(width, frames=1, side=14):
    spatial = width // 16 * 6
    temporal = width // 16 * 4
    w = np.tile(sincos(spatial, np.arange(side)), (frames * side, 1))
    h = np.tile(np.repeat(sincos(spatial, np.arange(side)), side, axis=0), (frames, 1))
    t = np.repeat(sincos(temporal, np.arange(frames)), side * side, axis=0)
    return np.concatenate([np.zeros((1, width)), np.concatenate([w, h, t], axis=1)], axis=0).astype(np.float32)


def build_encoder(config):
    import torch
    from torch import nn
    width, heads = config['embed_dim'], config['num_heads']

    class Attention(nn.Module):
        def __init__(self):
            super().__init__()
            self.qkv = nn.Linear(width, 3 * width)
            self.proj = nn.Linear(width, width)

        def forward(self, x):
            b, n, _ = x.shape
            q, k, v = self.qkv(x).reshape(b, n, 3, heads, width // heads).permute(2, 0, 3, 1, 4).unbind(0)
            a = torch.nn.functional.scaled_dot_product_attention(q, k, v)
            return self.proj(a.transpose(1, 2).reshape(b, n, width))

    class Mlp(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc1 = nn.Linear(width, 4 * width)
            self.fc2 = nn.Linear(4 * width, width)

        def forward(self, x):
            return self.fc2(torch.nn.functional.gelu(self.fc1(x)))

    class Block(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm1, self.norm2 = nn.LayerNorm(width), nn.LayerNorm(width)
            self.attn, self.mlp = Attention(), Mlp()

        def forward(self, x):
            x = x + self.attn(self.norm1(x))
            return x + self.mlp(self.norm2(x))

    class Patch(nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = nn.Conv3d(6, width, (1, 16, 16), stride=(1, 16, 16))

        def forward(self, x):
            return self.proj(x).flatten(2).transpose(1, 2)

    class CoordinateScale(nn.Module):
        def __init__(self):
            super().__init__()
            self.scale = nn.Parameter(torch.ones(1))

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.patch_embed = Patch()
            self.cls_token = nn.Parameter(torch.zeros(1, 1, width))
            self.register_buffer('pos_embed', torch.zeros(1, config['num_frames'] * 196 + 1, width))
            self.blocks = nn.ModuleList([Block() for _ in range(config['depth'])])
            self.norm = nn.LayerNorm(width)
            for key, name in [('time', 'temporal_embed_enc'), ('location', 'location_embed_enc')]:
                if key in config.get('coords_encoding', []):
                    setattr(self, name, CoordinateScale())

        def before_norm(self, image, temporal=None, location=None):
            # Published adapter permits single-frame inputs and interpolates 14x14
            # positions bicubically. Retain original spatial coordinate span.
            b, _, t, height, spatial_width = image.shape
            if image.shape[1] != 6 or height % 16 or spatial_width % 16:
                raise ValueError('Expected six HLS bands and patch-divisible image')
            pos = torch.from_numpy(position_encoding(width, t)).to(image.device)
            p = pos[1:].reshape(t, 14, 14, width).permute(0, 3, 1, 2)
            p = torch.nn.functional.interpolate(p, (height // 16, spatial_width // 16), mode='bicubic', align_corners=True)
            p = p.permute(0, 2, 3, 1).reshape(1, -1, width)
            x = self.patch_embed(image) + p
            if temporal is not None and hasattr(self, 'temporal_embed_enc'):
                tc = np.asarray(temporal)
                a = np.concatenate([sincos(width // 2, tc[:, :, 0]), sincos(width // 2, tc[:, :, 1])], axis=1)
                a = torch.from_numpy(a.reshape(b, t, width)).to(x).repeat_interleave(x.shape[1] // t, dim=1)
                x = x + self.temporal_embed_enc.scale * a
            if location is not None and hasattr(self, 'location_embed_enc'):
                a = np.concatenate([sincos(width // 2, location[:, 0]), sincos(width // 2, location[:, 1])], axis=1)
                x = x + self.location_embed_enc.scale * torch.from_numpy(a[:, None]).to(x)
            x = torch.cat([self.cls_token.expand(b, -1, -1), x], dim=1)
            for block in self.blocks:
                x = block(x)
            return x

        def forward(self, image, temporal=None, location=None):
            return self.norm(self.before_norm(image, temporal, location))

    return Encoder()


def download_checkpoint(record):
    """Bounded RAM download avoids a second full checkpoint on tiny local disks."""
    url = 'https://huggingface.co/' + record['repository'] + '/resolve/' + record['revision'] + '/' + record['file']
    stream = io.BytesIO()
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response:
        while chunk := response.read(1024 * 1024):
            if stream.tell() + len(chunk) > record['bytes']:
                raise ValueError('Pretrained file exceeds published size')
            stream.write(chunk)
            digest.update(chunk)
    if stream.tell() != record['bytes'] or digest.hexdigest() != record['sha256']:
        raise ValueError('Pretrained checkpoint checksum/size differs from pinned upstream')
    stream.seek(0)
    return stream


def extract(root, config_path):
    import torch
    from datetime import datetime, timezone
    root = Path(root)
    config = json.loads(Path(config_path).read_text())
    torch.set_num_threads(config['threads'])
    folder = root / 'data/pretrained-models'
    patches = folder / 'hls-patches'
    manifest = json.loads((patches / 'manifest.json').read_text())
    records = manifest['records']
    if not records:
        raise ValueError('No real HLS patches acquired')
    images, temporal, coords = [], [], []
    for r in records:
        path = patches / (r['cell_id'] + '.npz')
        if hashlib.sha256(path.read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('HLS subset integrity failure')
        when = datetime.fromisoformat(r['observation_time'].replace('Z', '+00:00'))
        if when.year != 2017:
            raise ValueError('Static landscape must precede all supervised years')
        with np.load(path) as a:
            image = a['reflectance'].astype(np.float32)
            images.append((image, a['good']))
        temporal.append([[when.year, when.timetuple().tm_yday]])
        coords.append([r['latitude'], r['longitude']])
    for record in config['models']:
        out = folder / (record['id'] + '-tokens.npz')
        if out.exists():
            meta = json.loads(out.with_suffix('.json').read_text())
            if meta['model'] != record or hashlib.sha256(out.read_bytes()).hexdigest() != meta['token_sha256']:
                raise ValueError('Cached external encoder identity/integrity mismatch')
            if meta['hls_manifest_sha256'] != hashlib.sha256((patches / 'manifest.json').read_bytes()).hexdigest():
                raise ValueError('Cached HLS population changed; use a new token cache')
            print('Cached pretrained tokens', record['id'], flush=True)
            continue
        cfg = json.loads((folder / record['repository'].split('/')[-1] / 'config.json').read_text())['pretrained_cfg']
        with download_checkpoint(record) as stream:
            checkpoint = torch.load(stream, map_location='cpu', weights_only=True)
        if 'state_dict' in checkpoint:
            checkpoint = checkpoint['state_dict']
        encoder_state = {k.removeprefix('encoder.'): v for k, v in checkpoint.items() if k.startswith('encoder.')}
        if not encoder_state:
            raise ValueError('Expected published Prithvi encoder state')
        model = build_encoder(cfg)
        model.load_state_dict(encoder_state, strict=True)
        model.eval()
        del checkpoint, encoder_state
        mean = np.asarray(cfg['mean'], np.float32)[:, None, None]
        std = np.asarray(cfg['std'], np.float32)[:, None, None]
        data = np.stack([np.where(good[None], (image - mean) / std, 0.) for image, good in images])[:, :, None]
        tokens = []
        with torch.inference_mode():
            for i in range(0, len(data), 32):
                tokens.append(model.before_norm(torch.from_numpy(data[i:i+32]), np.asarray(temporal[i:i+32]), np.asarray(coords[i:i+32])).numpy())
        np.savez_compressed(out, tokens=np.concatenate(tokens), cell_id=np.asarray([r['cell_id'] for r in records]),
                            norm_weight=model.norm.weight.detach().numpy(), norm_bias=model.norm.bias.detach().numpy())
        meta = {'model': record, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'token_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                'hls_manifest_sha256': hashlib.sha256((patches / 'manifest.json').read_bytes()).hexdigest(), 'config': cfg,
                'strict_encoder_load': True, 'encoder_parameter_count': sum(p.numel() for p in model.parameters()),
                'checkpoint_retained': False, 'retained': 'pre-normalization tokens at exact cached HLS patches and pretrained final LayerNorm parameters',
                'full_checkpoint_reproduction': 'Download the pinned source and verify its SHA256 again',
                'historical_encoder_availability': False, 'pretraining_geographic_overlap_unknown': 'v2' in record['id']}
        source_folder = folder / record['repository'].split('/')[-1]
        meta['upstream_file_sha256'] = {name: hashlib.sha256((source_folder / name).read_bytes()).hexdigest() for name in ['config.json', 'prithvi_mae.py', 'README.md']}
        meta['adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        out.with_suffix('.json').write_text(json.dumps(meta, indent=2))
        print('Extracted actual pretrained encoder', record['id'], 'cells', len(data), flush=True)
        del model


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', nargs='?', choices=['discover', 'extract'], default='extract')
    parser.add_argument('--root', default='.')
    parser.add_argument('--config', default='configs/pretrained-transfer.json')
    args = parser.parse_args()
    discover(args.root, args.config) if args.operation == 'discover' else extract(args.root, args.config)
