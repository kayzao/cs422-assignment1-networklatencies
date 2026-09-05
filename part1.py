#!/usr/bin/env python3
"""CS 422 Assignment 1, Part 1: CSV -> ping -> distances -> PDF plot (macOS)."""

import csv
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


FIELDS = [
    "host", "ip", "is_self", "latitude", "longitude", "distance_km",
    "transmitted", "received", "packet_loss_pct", "min_rtt_ms", "avg_rtt_ms",
    "max_rtt_ms", "ping_status", "geo_status", "error", "measured_at_utc",
]

# Edit these settings here; the script needs no command-line arguments.
INPUT_FILE = Path(__file__).resolve().parent / "data/listed_iperf3_servers.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"
PINGS_PER_IP = 10


def read_hosts(path):
    """Read the website's export; iPerf ports are irrelevant to ICMP ping."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if "IP/HOST" not in (reader.fieldnames or []):
            raise ValueError("Input CSV must contain an IP/HOST column.")
        hosts = list(dict.fromkeys(
            host for row in reader if (host := (row.get("IP/HOST") or "").strip())
        ))
    if not hosts:
        raise ValueError("Input CSV contains no destinations.")
    return hosts


def resolve_ips(host):
    """Keep this experiment IPv4-only; include all returned DNS A addresses."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        answers = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
        return sorted({answer[4][0] for answer in answers}, key=ipaddress.IPv4Address)
    if address.version != 4:
        raise ValueError("This script measures IPv4 only.")
    return [str(address)]


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "cs422-assignment1/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data
    except (URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"Lookup failed at {url}: {exc}") from exc


def locate_ip(ip):
    """Use the same public geolocation source for the origin and destinations."""
    data = fetch_json(f"https://ipwho.is/{ip}")
    if data.get("success") is not True:
        raise RuntimeError(data.get("message", "Geolocation failed"))
    try:
        latitude, longitude = float(data["latitude"]), float(data["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Geolocation response has no valid coordinates") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise RuntimeError("Geolocation coordinates are outside valid ranges")
    return {"ip": ip, "latitude": latitude, "longitude": longitude,
            "city": data.get("city", ""), "country": data.get("country", "")}


def distance_km(origin, destination):
    """Haversine great-circle distance; this is not the cable's route length."""
    lat1, lon1 = map(math.radians, (origin["latitude"], origin["longitude"]))
    lat2, lon2 = map(math.radians, (destination["latitude"], destination["longitude"]))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def parse_ping(output):
    """Read macOS's summary, including late replies counted by ping itself."""
    stats = {}
    packets = re.search(
        r"(\d+) packets transmitted,\s*(\d+) packets received,.*?([\d.]+)% packet loss",
        output,
    )
    if packets:
        stats.update(transmitted=int(packets[1]), received=int(packets[2]),
                     packet_loss_pct=float(packets[3]))
    rtt = re.search(
        r"round-trip min/avg/max/stddev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
        output,
    )
    if rtt:
        stats.update(min_rtt_ms=float(rtt[1]), avg_rtt_ms=float(rtt[2]),
                     max_rtt_ms=float(rtt[3]))
    return stats


def ping_ip(ip, count, log):
    # On macOS -W is milliseconds; -t is a total deadline in seconds.
    command = ["/sbin/ping", "-n", "-c", str(count), "-i", "1", "-W", "2000",
               "-t", str(count + 5), ip]
    error = ""
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                env={**os.environ, "LC_ALL": "C"}, timeout=count + 10)
        output = result.stdout + result.stderr
        returncode = result.returncode
    except subprocess.TimeoutExpired as exc:
        chunks = [exc.stdout or b"", exc.stderr or b""]
        output = "".join(c.decode(errors="replace") if isinstance(c, bytes) else c
                         for c in chunks)
        error, returncode = "Ping exceeded the process timeout", None
    except OSError as exc:
        output, error, returncode = "", str(exc), None
    log.write(f"\n$ {' '.join(command)}\n{output}\nexit={returncode}; {error}\n")
    log.flush()
    stats = parse_ping(output)
    if error:
        status = "error"
    elif stats.get("received") == 0:
        status = "non_responsive"
    elif stats.get("received", 0) > 0 and "avg_rtt_ms" in stats:
        status = "ok" if stats.get("transmitted") == count else "incomplete"
    else:
        status, error = "error", f"No usable ping summary (exit {returncode}); see ping.log"
    return {**stats, "ping_status": status, "error": error}


def plot_results(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = [r for r in rows if r.get("ping_status") == "ok"
             and r.get("geo_status") == "ok" and r.get("avg_rtt_ms") is not None]
    fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
    for is_self, label, color, marker in [
        (False, "Server: mean RTT", "#2563eb", "o"),
        (True, "Own public IP: mean RTT", "#c2410c", "D"),
    ]:
        group = [r for r in valid if r["is_self"] == is_self]
        if group:
            x = [r["distance_km"] for r in group]
            means = [r["avg_rtt_ms"] for r in group]
            # One point per destination; whiskers show the measured min-to-max range.
            ax.errorbar(x, means, yerr=[
                [r["avg_rtt_ms"] - r["min_rtt_ms"] for r in group],
                [r["max_rtt_ms"] - r["avg_rtt_ms"] for r in group],
            ], fmt=marker, markersize=4, color=color, ecolor=color,
                elinewidth=0.7, capsize=2, alpha=0.65, label=label)
    if valid:
        ax.legend(fontsize=9)
    else:
        ax.text(0.5, 0.5, "No destinations have both usable RTT and location data.",
                transform=ax.transAxes, ha="center", va="center", wrap=True)
    ax.set(title=f"Distance vs RTT ({len(valid)} destinations; whiskers: min-max)",
           xlabel="Estimated geographic distance (km)", ylabel="Round-trip time (ms)")
    ax.set_xlim(left=-100)
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.2)
    fig.savefig(path)
    plt.close(fig)
    return len(valid)


def main():
    # Check that this Mac is ready to run the experiment.
    if sys.platform != "darwin":
        raise RuntimeError("This script uses the macOS ping command.")
    if PINGS_PER_IP < 1:
        raise ValueError("PINGS_PER_IP must be positive.")

    # Load every destination from the CSV configured at the top of this file.
    hosts = read_hosts(INPUT_FILE)

    # Estimate the starting coordinates from the current public IP automatically.
    print("Detecting public IPv4 address and estimating your location...", flush=True)
    public_ip = str(ipaddress.IPv4Address(fetch_json("https://api.ipify.org?format=json")["ip"]))
    origin = locate_ip(public_ip)
    # Give each run its own folder and record the settings used for these measurements.
    started = datetime.now(timezone.utc)
    output = OUTPUT_DIR / started.strftime("%Y%m%dT%H%M%S_%fZ")
    output.mkdir(parents=True, exist_ok=False)
    print(f"Origin: {public_ip} ({origin['city']}, {origin['country']})")
    print(f"Results: {output.resolve()}\nMeasuring {len(hosts)} CSV hosts plus your public IP.", flush=True)
    metadata = {"started_at_utc": started.isoformat(), "input": str(INPUT_FILE.resolve()),
                "count": PINGS_PER_IP, "origin": origin,
                "geolocation_source": "https://ipwhois.io/documentation",
                "address_family": "IPv4", "ping_interval_seconds": 1,
                "reply_wait_ms": 2000}
    (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    rows, seen = [], set()
    with (output / "rtt_results.csv").open("w", newline="", encoding="utf-8") as table, \
            (output / "ping.log").open("w", encoding="utf-8") as log:
        writer = csv.DictWriter(table, fieldnames=FIELDS)
        writer.writeheader()
        # Own address first guarantees it is labelled even if it also appears in the CSV.
        for host in [public_ip] + hosts:
            try:
                ips = resolve_ips(host)
            except (OSError, ValueError) as exc:
                row = {"host": host, "ping_status": "dns_error", "error": str(exc)}
                rows.append(row)
                writer.writerow(row)
                table.flush()
                print(f"{host}: resolution failed: {exc}", flush=True)
                continue
            # A hostname can resolve to multiple IPs; measure each unique address once.
            for ip in ips:
                if ip in seen:
                    log.write(f"\nSkipped duplicate: {host} -> {ip}\n")
                    continue
                seen.add(ip)
                print(f"[{len(seen)}] {host} -> {ip}: pinging...", flush=True)
                row = {"host": host, "ip": ip, "is_self": ip == public_ip,
                       "measured_at_utc": datetime.now(timezone.utc).isoformat()}
                # Wait for all PINGS_PER_IP probes, then parse the batch summary.
                row.update(ping_ip(ip, PINGS_PER_IP, log))
                try:
                    # Reuse our own coordinates; look up each server and calculate its distance.
                    location = origin if ip == public_ip else locate_ip(ip)
                    row.update(latitude=location["latitude"], longitude=location["longitude"],
                               distance_km=round(distance_km(origin, location), 3), geo_status="ok")
                except RuntimeError as exc:
                    row.update(geo_status="error", error="; ".join(filter(None, [row["error"], str(exc)])))
                # Save each completed result immediately so an interrupted run keeps its data.
                rows.append(row)
                writer.writerow(row)
                table.flush()
                print(f"    ping={row['ping_status']}; location={row['geo_status']}; "
                      f"mean RTT={row.get('avg_rtt_ms', 'unavailable')} ms", flush=True)
    # Once all destinations are processed, plot those with usable RTT and location data.
    plotted = plot_results(rows, output / "distance_vs_rtt.pdf")
    print(f"Done: {len(seen)} unique IPs attempted; {plotted} plotted. Files: {output.resolve()}")
    if not plotted:
        print("No usable plot data. Review rtt_results.csv and ping.log.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped. Completed rows and logs are preserved; plot generation was not completed.", file=sys.stderr)
        sys.exit(130)
