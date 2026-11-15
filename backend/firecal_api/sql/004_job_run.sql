-- State of scheduled background jobs (firecal_api/schedule.py), e.g. the monthly weather fetch.
-- No row (or no last_ok) means the job never finished, so it runs right away.
create table if not exists job_run (
  job          text primary key,
  last_ok      timestamptz,          -- end of the last run that finished completely
  last_attempt timestamptz,          -- start of the last run, finished or not
  last_result  text                  -- 'running', 'ok', or why the run did not finish
);
