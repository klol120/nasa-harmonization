# External pretrained model review

Reviewed 15 November 2026. Predictor acquisition and supervised training remain
NASA-only. Checkpoints/software can be hosted by their authors on Hugging Face or
GitHub; those hosts are not additional environmental data providers. No published
score is treated as our result.

| Candidate | Published weights / license | Input and task check | Decision |
|---|---|---|---|
| [IBM/NASA Prithvi EO 1.0 100M](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-1.0-100M) | Apache-2.0; pinned 453,671,052-byte checkpoint | Self-supervised NASA HLS Landsat imagery from the contiguous US; six surface-reflectance bands, supports one frame | Adapt an image encoder, not an existing fire classifier |
| [IBM/NASA Prithvi EO 2.0 Tiny TL](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-tiny-TL) | Apache-2.0; pinned 129,258,736-byte encoder/decoder checkpoint | NASA HLS global pretraining; temporal/location encodings; roughly 5M encoder parameters | Adapt and compare with larger encoders |
| [IBM/NASA Prithvi EO 2.0 100M TL](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-100M-TL) | Apache-2.0; pinned 454,660,610-byte checkpoint | Same six physical HLS bands; wider encoder, global pretraining | Adapt; validate actual weight dimensions because card config architecture string is misleading |
| [Greek uncertainty-aware forecasting](https://github.com/Orion-AI-Lab/uncertainty-wildfires) | Actual deterministic, Bayesian and ensemble `.pth` weights exist in `trained_models`; repository license not established by a README claim | Mixed-source Greek predictors, including non-NASA data; published danger labels and feature contract differ | Do not silently relax NASA-only restriction or assume reuse rights |
| [Mesogeos temporal forecasting](https://github.com/Orion-AI-Lab/mesogeos) and [Greek 2022 models](https://github.com/Orion-AI-Lab/wildfire_forecasting) | Data/code and methodology available; original 2022 dataset requires about 250 GB unpacked per authors | ERA5/JRC/WorldPop/Copernicus/EFFIS and MODIS; large-fire danger differs from our occurrence target | Methodological reference; not a NASA-only pretrained experiment |
| [ECMWF Probability-of-Fire](https://github.com/ecmwf/AI-Probability-of-Fire) | Public author repository inspected | Uses ECMWF weather/fuel inputs; cannot substitute our POWER inputs without feature/distribution changes | Excluded from this NASA-only run |
| [Google next-day wildfire spread](https://github.com/google-research/google-research/tree/master/wildfire_conv_lstm) | Published implementation/checkpoint route | Requires known burning areas; predicts spread rather than general occurrence | Keep outside the current task |

`Prithvi-EO-2.0-tiny` currently resolves to the same revision and checkpoint as
`Prithvi-EO-2.0-tiny-TL`; these are not two distinct candidates. Each accepted
checkpoint's immutable revision, filename, exact size and SHA256 are in
[`pretrained-transfer.json`](../configs/pretrained-transfer.json). Metadata does not
prove successful weight acquisition; execution receipts/results record that.

## NASA inputs and model semantics

[NASA HLS Landsat L30 v2](https://hls.gsfc.nasa.gov/products/) supplies native 30m
reflectance. Discovery uses NASA CMR `C2021957657-LPCLOUD`; protected COG bands
and Fmask come from `data.lpdaac.earthdatacloud.nasa.gov`, requiring Earthdata
authentication. HLS is distributed without usage restrictions under the NASA
Earth science data policy; cite the product. No non-NASA predictor is added.

One native 32x32 crop at each recorded vegetation centroid samples a 960m square
within a roughly 10km forecasting cell. It cannot represent the whole cell or
provide 30m fire-risk predictions. Scene selection uses June–October 2017 and
catalogue cloud ordering, without outcomes. The same old landscape is used for all
supervised years, so it is a static proxy, not current fuel condition. Future work
needs spatial coverage and genuinely available time-varying imagery.

Keep six raw bands in the published order B02/B03/B04/B05/B06/B07 (Landsat narrow
NIR is B05), Fmask and source windows/URLs/versions/hashes. Use at least 95% clear,
valid land pixels. Clouds, cirrus, cloud adjacency, shadow, snow, water, fill and
high aerosol fail screening. Invalid residual pixels are replaced by the source
model's band mean after recording raw masks. Missing cells exclude their positive
and negative supervised rows together; they never turn into negative fire labels.

The upstream config means/stds are in raw scaled-reflectance units. Apply them to
raw integer values, not values already multiplied by 0.0001. Fine-tuning reuses
our ten-day historical weather/wetness and static/NDVI context, including the same
retrospective target-day weather proxy. Existing cloud/QA/conflict exclusions and
fourteen-day split gaps carry through unchanged.

## Fine-tuning design and scientific limits

Each external encoder supplies cached tokens **before its final LayerNorm**. One
arm freezes every encoder parameter and learns a Lebanese prediction head. The
other updates the original pretrained final LayerNorm scale/bias and a new head;
all attention blocks remain frozen. This is limited actual encoder fine-tuning,
not full-backbone fine-tuning or a pre-existing wildfire model. Caching frozen
operations is equivalent to rerunning those operations on each training example.

Fit heads and train-only preprocessing on 2018–2020, calibrate on natural 2021
prevalence, select models/thresholds on 2022, then freeze before diagnostic scoring
on known 2023–2025 and Jan–Oct 2026. Every arm uses the same image-qualified rows.
Seasonal, weather-only logistic, environment logistic and no-image neural controls
isolate some added-value claims. Weighted loss does not yield calibrated
probabilities; separate sigmoid calibration is still distribution-dependent.

There is no zero-shot fire probability: an unsupervised image encoder has no fire
occurrence head. Modern pretrained weights were unavailable in historical years.
EO2 uses global imagery and Lebanese pretraining overlap cannot be ruled out. Even
the US-pretrained v1 checkpoint became available later than our fitting years.
Reprocessed HLS dates are observation dates, not proof of historical availability.
Previously viewed tests and repeated validation searches are further limitations.
These scores cannot be advertised as prospective operational forecast skill.

## Implementation attribution

Encoder attention/MLP keys and position interpolation follow the pinned
IBM/NASA `prithvi_mae.py` implementations accompanying the checkpoints. Their
source header is Copyright IBM Corp. 2024, Apache License 2.0. Our adapter omits
the reconstruction decoder, masking and training-only dropout; it implements
CPU attention in native PyTorch, supports strict full encoder state loading and
caches pre-final-normalization tokens. This is a modified implementation, not
unmodified upstream code. Checksum verification and `torch.load(weights_only=True)`
are mandatory; remote repository code is never dynamically executed.

The large source checkpoints are downloaded into bounded RAM, verified and released
after extraction. Exact HLS subsets, extracted tokens, original final LayerNorm
parameters, trained heads and manifests are retained. Rebuilding for a new image
requires downloading the pinned checkpoint again. This deliberate storage choice
does not claim complete upstream checkpoint files are cached locally.
