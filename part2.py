import os
from pathlib import Path
import random
import re
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from part1 import INPUT_FILE, read_hosts, resolve_ips


def parse_trace(text, destination):
    """Average replies at each responding hop and check that the destination replied."""
    hops = []
    for line in text.splitlines():
        fields = line.split()
        if not fields or not fields[0].isdigit():
            continue

        address = ""
        replies, destination_replies = [], []
        for index, field in enumerate(fields):
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", field):
                address = field
            if field == "ms":
                # An exclamation mark indicates an ICMP error, not a successful reply.
                if index + 1 < len(fields) and fields[index + 1].startswith("!"):
                    continue
                rtt = float(fields[index - 1])
                replies.append(rtt)
                if address == destination:
                    destination_replies.append(rtt)

        if replies:
            values = destination_replies or replies
            hops.append({"hop": int(fields[0]), "rtt_ms": sum(values) / len(values)})
        if destination_replies:
            return hops
    return []


def trace_ip(ip):
    """Run traceroute and return the measurements."""
    # ICMP probes, numeric addresses, 30 hops, three probes per hop, two-second waits.
    command = ["traceroute", "-I", "-n", "-m", "30", "-q", "3", "-w", "2", ip]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True,
                                env={**os.environ, "LC_ALL": "C"}, timeout=190)
    except subprocess.TimeoutExpired:
        return []

    return parse_trace(result.stdout, ip)


def plot_results(results, output_dir):
    fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
    labels_used = set()
    for index, result in enumerate(results):
        previous = positive = negative = 0
        for hop in result["hops"]:
            # Traceroute RTTs are cumulative. Differences estimate extra delay.
            # Across missing hops, a difference covers the entire gap.
            number = hop["hop"]
            delta = hop["rtt_ms"] - previous
            previous = hop["rtt_ms"]
            bottom = positive if delta >= 0 else negative
            label = f"Hop {number}" if number not in labels_used else None
            ax.bar(index, delta, bottom=bottom, label=label,
                   color=plt.get_cmap("turbo")((number - 1) / 29))
            labels_used.add(number)
            if delta >= 0:
                positive += delta
            else:
                negative += delta

    ax.set_xticks(range(len(results)), [r["destination"] for r in results], rotation=20)
    ax.set(xlabel="Destination IPv4", ylabel="Change in RTT (ms)",
           title=f"Estimated hop latency breakdown ({len(results)} destinations)")
    ax.axhline(0, color="black", linewidth=0.6)
    if labels_used:
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8, ncol=2)
    fig.supxlabel("Signed RTT changes since the previous responding hop; gaps combine missing hops.\n"
                  "Estimates, not measured link delays. Positive + negative stacks = destination RTT.",
                  fontsize=9)
    fig.savefig(output_dir / "hop_latency_breakdown.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    for result in results:
        destination = result["hops"][-1]
        # Use the destination TTL, so missing intermediate replies still count as hops.
        ax.scatter(destination["hop"], destination["rtt_ms"], label=result["destination"])
    if results:
        ax.legend(title="Destination IPv4")
    ax.set(xlabel="Hop count (including non-responsive hops)", ylabel="Mean destination RTT (ms)",
           title=f"Hop count vs RTT ({len(results)} destinations)")
    ax.grid(alpha=0.2)
    fig.savefig(output_dir / "hop_count_vs_rtt.pdf")
    plt.close(fig)


def main():
    output_dir = Path(sys.argv[1])

    print("Resolving the CSV destinations for Part 2", flush=True)
    ips = set()
    for host in read_hosts(INPUT_FILE):
        try:
            ips.update(resolve_ips(host))
        except (OSError, ValueError) as error:
            print(f"Skipping {host}: {error}", file=sys.stderr)
    selected = random.sample(sorted(ips), 5)

    results = []
    for ip in selected:
        print(f"Tracing {ip}", flush=True)
        hops = trace_ip(ip)
        if hops:
            results.append({"destination": ip, "hops": hops})
        else:
            print(f"{ip}: non-responsive", flush=True)
    plot_results(results, output_dir)
    print(f"Part 2 plots saved to {output_dir}")


if __name__ == "__main__":
    main()
