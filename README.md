# cs422-assignment1-networklatencies

Measuring network latencies for CS 422 Assignment 1, Part 1, on macOS.
One Python script reads the exported server CSV, measures ping RTTs, estimates
geographic distances, and generates a PDF scatter plot. Part 2 is not implemented.

## Setup

Use macOS and Python 3.9 or newer. From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The input at `data/listed_iperf3_servers.csv` is the supplied, unchanged export from
[iperf3serverlist.net](https://iperf3serverlist.net/). To refresh it, download the
website's CSV export and replace that file. No API keys or sudo are needed.

## Run Part 1

```bash
python part1.py
```

The script takes no command-line arguments. It reads the exported CSV file and
uses 10 ping attempts per unique IPv4 address. To change the settings, edit these
constants near the top of `part1.py`:

- `INPUT_FILE`: the CSV file to read.
- `OUTPUT_DIR`: the folder in which to save each run.
- `PINGS_PER_IP`: the number of probes per IP (10 by default).

Input and output paths are relative to the script's location, so running it from
another directory works too. Use at least 10 pings per IP for submission.
Measurements run sequentially, at one ping per second. Expect roughly 30-40 minutes
for the supplied 190-row export when servers respond, with longer runs possible
because of timeouts, slow lookups, or hostnames resolving to multiple addresses.

## What the script does

1. Reads `IP/HOST`; trims blanks and removes identical entries. iPerf ports are ignored.
2. Gets your current public IPv4 address from [ipify](https://www.ipify.org/) and
   estimates its coordinates using [IPWhois](https://ipwhois.io/documentation).
3. Resolves hostnames to all returned IPv4 (A) addresses and pings each unique IP,
   including your own. IPv6 is outside this scaffold's scope.
4. Parses macOS ping's packet counts, loss, and min/mean/max RTT summary in milliseconds.
5. Looks up destination coordinates with IPWhois and computes great-circle distance
   using the haversine formula and a mean Earth radius of 6371.0088 km.
6. Writes results and a scatter plot: one mean-RTT point per destination, with
   vertical whiskers from minimum to maximum RTT. Your public IP has a distinct marker.

The functions follow this same order in `part1.py` for code references in the report.
Only Matplotlib is an added dependency; networking and data processing use Python's
standard library and the macOS `/sbin/ping` command.

## Outputs

Each run creates a new UTC timestamped directory under the configured `OUTPUT_DIR` (initially `results/`):

- `rtt_results.csv`: host, IP, self marker, coordinates, distance, RTT statistics,
  packet counts/loss, statuses, errors, and measurement time.
- `distance_vs_rtt.pdf`: distance versus mean RTT, with minimum/maximum whiskers.
- `ping.log`: commands and raw ping output; also records duplicate resolved IPs.
- `run.json`: input path, measurement settings, start time, estimated origin, and source.

Unreachable servers retain blank RTT fields, never zero RTT. DNS failures are recorded.
Failed geolocation retains any successful RTT measurement but excludes that destination
from the plot. If no points are usable, the PDF explains this and the script exits with
status 1. An origin lookup failure stops the run because distances cannot be estimated.
Completed rows and ping logs are flushed after each IP; interrupting the run preserves
these files, but does not generate the final plot.

## Interpreting the experiment

IP geolocation is approximate and can reflect an ISP or VPN location rather than your
physical position. Geographic distance is not the actual network route length. The
own-IP point has zero estimated distance because it uses the same origin coordinates;
its RTT is still measured, and it may be non-responsive or represent your router.

Statistics use received replies, so interpret them alongside sample count and packet
loss. The script provides the measurements for 1(a) and plot for 1(b); write your own
interpretation for 1(c) from the actual run. Minimum RTT approaches the least delayed
observed round trip; maximum RTT can reflect transient delays as well as routing and
endpoint behavior. Neither statistic measures physical distance directly.

IPWhois's free API has usage limits; HTTP or API errors are recorded without inventing
coordinates. See the linked API documentation for current limits.
