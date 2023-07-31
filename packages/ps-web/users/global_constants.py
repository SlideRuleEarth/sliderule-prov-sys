import os
FMT_Z  = "%Y-%m-%dT%H:%M:%SZ"
FMT    = "%Y-%m-%dT%H:%M:%S%Z"
FMT_z  = "%Y-%m-%dT%H:%M:%S%z" # %z is offset where Z is equivalent to +00:00
FMT_TZ = "%Y-%m-%d %H:%M:%S %Z"

FMT_MONTHLY = "%Y-%m"
FMT_DAILY = "%Y-%m-%d"
FMT_HOURLY = "%Y-%m-%dT%H:%M"

DISPLAY_EXP_TM=363
DISPLAY_EXP_TM_MARGIN=14


NULL_CCR = '{"":""}'

MIN_HRS_TO_LIVE_TO_START = 24
MIN_TTL = 15
MAX_TTL = 720
COOLOFF_SECS=int(os.environ.get("COOLOFF_SECS",default=1))
PROVISIONING_DISABLED = False
