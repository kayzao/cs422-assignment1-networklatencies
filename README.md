# cs422-assignment1-networklatencies

CS 422 Assignment 1, Part 1: measure network round-trip time (RTT) and compare it
with geographic distance. The macOS/Linux Python script reads a server CSV, includes
your public IP, and generates statistics and a **PNG scatter plot at 300 DPI**.
Part 2: TODO

## Setup and run

Use macOS or Linux with Python 3.9 or newer. From the repository folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python part1.py
```

[Matplotlib](requirements.txt) is the only added dependency. The script uses
Python's standard library for file handling and web requests, and the system's
`ping` program for measurements. It detects macOS or Linux automatically and finds
`ping` on PATH. Linux requires **iputils ping** (for example, the `iputils-ping`
package on Debian/Ubuntu). Minimal Linux containers may need ping installed and
permission to send ICMP packets. No API keys are needed.

The script takes no command-line arguments. Change the [settings near the top of
part1.py](part1.py#L27-L31) if needed:

| Setting | Current value |
| --- | --- |
| `INPUT_FILE` | `data/listed_iperf3_servers.csv`, beside the script |
| `OUTPUT_DIR` | `results/`, beside the script |
| `PINGS_PER_IP` | 10 |

The input is the [CSV exported from the server list](data/listed_iperf3_servers.csv).
To refresh it, download a CSV from [iperf3serverlist.net](https://iperf3serverlist.net/)
and replace that file. The `IP/HOST` column is required; iPerf ports are not used.
The configured paths are based on the script's location, so it also works when
launched from another folder.

Each progress message covers a batch of 10 probes. The [ping command](part1.py#L156-L169)
sends them one second apart, so a responsive IP usually takes about 9-10 seconds,
plus lookup time. The ping deadline is 15 seconds at the current count, with a
20-second Python timeout as a backup. The script uses macOS or Linux timing flags
automatically and accepts both platforms' summary formats. These waits are separate from the measured
RTT, which is recorded in milliseconds. Expect roughly 30-40 minutes for the
supplied 190-row export when servers respond; timeouts, slow lookups, and hostnames
with multiple addresses can make the run longer.

## Part 1(a): ping statistics and coordinates

The [main() function](part1.py#L247-L324) runs the complete experiment:

1. [read_hosts()](part1.py#L34-L49) reads `IP/HOST` from the CSV, trims whitespace,
   skips blanks, and removes identical entries.
2. [Public IP detection in main()](part1.py#L261-L262) uses
   [ipify](https://www.ipify.org/) to find the current public IPv4 address and
   estimates its location automatically. [resolve_ips()](part1.py#L52-L65)
   translates hostnames into IPv4 addresses. The [measurement loop](part1.py#L284-L304)
   includes your public IP and tests each unique resolved address once.
3. [ping_ip()](part1.py#L149-L200) runs the system ping program and saves its raw
   output. [parse_ping()](part1.py#L122-L146) extracts transmitted/received counts,
   packet loss, and minimum, average, and maximum RTT. It reads statistics already
   calculated by ping using regular expressions (text patterns).
4. [locate_ip()](part1.py#L88-L106) obtains approximate latitude and longitude from
   [IPWhois](https://ipwhois.io/documentation) for both the origin and destinations.
   [fetch_json()](part1.py#L68-L85) makes the web request and converts the JSON
   response into Python data.

This implementation measures IPv4 only. A hostname may resolve to several IPv4
addresses, so the number of measured IPs can differ from the number of CSV rows.

## Part 1(b): distance versus RTT

[distance_km()](part1.py#L109-L119) calculates geographic distance from the two
latitude/longitude pairs. It uses the haversine formula to account for Earth's
curvature, with a mean Earth radius of 6371.0088 km.

[plot_results()](part1.py#L203-L244) generates the scatter plot using Matplotlib:

- **X-axis:** estimated geographic distance in kilometres.
- **Y-axis:** average RTT in milliseconds, with one point per destination IP.
- **Vertical whiskers:** the minimum-to-maximum RTT range, not a confidence interval.
- **Orange diamond:** your own public IP; blue circles represent servers.

Only destinations with usable ping statistics and geolocation data are plotted.
The [save operation](part1.py#L242) sets 300 DPI, and the
[call from main()](part1.py#L319) supplies the filename `distance_vs_rtt.png`.

## Output files and failures

Each run creates a new UTC timestamped directory under `OUTPUT_DIR`. The
[run setup](part1.py#L264-L275) records the settings, and the
[result-writing code](part1.py#L301-L315) saves each completed measurement.

| File | Contents |
| --- | --- |
| `rtt_results.csv` | Host, IP, self marker, coordinates, distance, min/average/max RTT, packet counts/loss, statuses, errors, and measurement time. See the [column definitions](part1.py#L21-L25). |
| `distance_vs_rtt.png` | The 300-DPI scatter plot of distance versus RTT. |
| `ping.log` | Commands and raw ping output, plus skipped duplicate addresses. |
| `run.json` | Input path, ping count and timing settings, start time, estimated origin, operating system, and geolocation source. |

[Ping failure handling](part1.py#L179-L200) distinguishes command errors from
non-responsive destinations. Missing RTT values remain blank instead of becoming zero.
[DNS failures](part1.py#L285-L293) are recorded and the run continues.
[Geolocation failures](part1.py#L305-L311), including API errors, preserve any ping
statistics but exclude that destination from the plot.

An origin lookup failure stops the run because distances cannot be estimated.
If no destinations have usable plot data, the PNG contains an explanatory message
and the script exits with status 1. Completed rows and logs are flushed to their
files as the run progresses; interrupting the script preserves those files but
does not generate the final plot.
