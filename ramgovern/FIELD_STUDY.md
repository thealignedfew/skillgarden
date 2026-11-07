# Paging Idle AI Sessions Out of RAM: A Field Study

First draft, 7 November 2026.

## Abstract

For eight days (31 October to 7 November 2026), a scheduled Working Set Governor paged idle AI coding sessions out of RAM every five minutes. The machine was a 64 GB workstation running 96 to 112 concurrent Claude Code sessions.

- **Volume:** the Governor ran 1,810 scheduled sweeps and 1,990 post-turn trims, covering 82,549 process trims in all.
- **Memory:** a typical sweep released 180 to 680 MB of resident memory (daily medians). Summed over all sweeps, that is about 800 GB of pages moved out of RAM.
- **Page-in bursts:** trimming did not cause the machine's page-in bursts. A controlled A/B test and an unplanned 13-hour shutdown both showed burst rates moving with overall load, not with trimming.
- **Display stalls:** samples with heavy late-frame rates fell from a mean of 6.0 percent in the five days before the Governor to under 0.3 percent after it. This is a before-and-after comparison, not a controlled one.
- **Cost:** the Governor spends about 1.5 CPU-seconds per run, near 0.03 percent of the processor's capacity.

## The problem

An idle AI coding session still holds its memory. Each Claude Code session is one `claude.exe` process. Between turns it sits waiting for its next prompt while keeping 100 to 300 MB resident. On the test machine, 109 sessions held about 13 GB of RAM together, most of it idle.

Many of these sessions run unattended. A timer re-prompts each one every 15, 30 or 50 minutes, so a session works for a minute or two and then waits for the rest of the interval. VS Code adds an extension host per window, and the extension that carries the AI sessions keeps that host busy on every scheduled turn.

Windows reclaims memory from idle processes only once memory is already short, and then from many processes at once. The window in use then slows down while the system pages. The Governor makes the same reclaim earlier and selectively: only processes that are idle, never the one in front.

## Test machine and workload

The test machine is a single high-end desktop. The session fleet grew during the study.

| Item | Value |
| --- | --- |
| Processor | Intel Core i9-13900K: 24 cores (8 performance, 16 efficiency), 32 threads, 3.0 GHz base, up to 5.8 GHz boost (manufacturer spec) |
| Memory | 64 GB DDR5-5600 (2 x 32 GB) |
| Storage | Two 1 TB NVMe SSDs, plus a 16 TB hard disk not used for paging |
| Operating system | Windows 11 Pro, build 26300 |
| Pagefile | 32 to 240 GB on the system SSD plus a system-managed file on a second drive. The commit limit grew from 178 to 203 GB over the period. |
| Claude Code sessions | 96 at the start, 101 to 112 in the last two days |
| Other AI sessions | 15 to 16 Codex sessions |
| VS Code | 141 to 155 processes, including 47 to 51 extension hosts |
| Candidates per sweep | Daily medians of 105 to 151 sessions and extension hosts (16 on 1 November, when most sessions were closed) |
| Scheduled turns | The post-turn hook fired 300 to 1,250 times a day, once for each unattended turn that ended |

The machine ran its normal daily work throughout. That load rose over the period: free RAM at the start of a sweep had a median of 10 to 12 GB on most days, fell to 9.8 GB on 6 November and to 4.9 GB on 7 November.

## Method

A trim is one Windows call, `EmptyWorkingSet`, on one process. The process's resident pages move to the standby list, then to the compressed store, then to the pagefile. The process keeps running and faults pages back in when it needs them, so nothing is killed and there is nothing to undo.

The Governor trims through two routes:

- **Scheduled sweep:** every 5 minutes, a scheduled task checks every candidate process.
- **Post-turn trim:** right after an unattended session finishes a scheduled turn, a hook trims that session's own process.

A sweep runs these steps:

1. **Collect candidates.** Stage 1 (31 October) takes every `claude.exe`. Stage 2 (from the evening of 31 October) adds VS Code extension-host processes.
2. **Idle test.** A candidate must use under 0.05 CPU-seconds in 10 seconds. It must also not have used more than 0.5 CPU-seconds since the previous run. An extension host must have been quiet for 10 minutes.
3. **Guards.** These are never trimmed:
   - the foreground window's process;
   - the Governor's own process chain;
   - processes younger than 2 minutes (sessions) or 10 minutes (extension hosts);
   - VS Code's main window, renderer and GPU processes;
   - any extension host that is the parent of a live AI session.
4. **Trim and watch.** The sweep trims, then samples for 30 seconds. It records resident memory and free RAM before, at 2 seconds and at 30 seconds, plus the system's peak page-in rate.
5. **Storm rule.** If a trimmed process climbs above half a CPU core for 10 seconds within those 30 seconds, the Governor writes a stop file and halts every later run until a person clears it.

Every run writes one log line. Those lines are this study's data. A separate validator sampled the system page-in rate every 10 seconds and judged the results each day.

## Results: memory released

A scheduled sweep released a median of 300 to 450 MB of resident memory on ordinary days, and about half of that was still released 30 seconds later.

The first day was higher (679 MB) because 31 October started from a fleet that had never been trimmed. On 1 November most sessions were closed, so there was little to take. The amount per sweep rose with the fleet, from 105 candidates a sweep to 151.

Post-turn trims added another 1,990 single-session trims over the period, each taking one session down right after its scheduled turn. By the next sweep 5 minutes later, the trimmed set had regrown a median of 150 to 240 MB. The Governor holds a lower floor by repeating, not by a one-time saving.

## Results: does trimming cause page-in bursts?

No. When trimming was switched off, the share of time spent in page-in bursts did not fall. It moved with the day's load, not with the Governor.

The question arose on days four and five. In the first days, 10-second samples above 10,000 page-ins per second were 9 to 10 points more common after post-turn trims than elsewhere. That comparison was confounded: post-turn trims fire right after a session's busy turn, which is when the machine is busiest anyway. Two tests separated the effects.

- **Controlled A/B test, from 5 November 01:30.** Post-turn trims were switched off in odd-numbered hours and left on in even hours; the scheduled sweeps ran in both.
- **Natural control, 6 November.** The storm rule halted the Governor from 01:39 to 14:33. For almost 13 hours there were no trims of any kind.

| Condition | Samples above 10,000 page-ins/s |
| --- | --- |
| A/B, 6 Nov 14:34 to 24:00: post-turn trims off (odd hours) | 17.6% |
| A/B, 6 Nov 14:34 to 24:00: post-turn trims on (even hours) | 18.2% |
| No trims at all, 6 Nov 01:39 to 14:33 (halt) | 9.9% |
| Same hours with the Governor running, 4 Nov | 8.4% |
| Same hours with the Governor running, 5 Nov | 15.3% |

The A/B gap is 0.6 points, within day-to-day noise, and 5 November's first A/B day pointed the same way. During the halt, 5 of the day's 12 highest page-in samples (up to 85,823 per second) arrived with no trim for hours. Swings between days are far larger than any difference the Governor makes.

## Results: display stalls before and after

The same machine was monitored for five days before the Governor existed. A separate monitor recorded, every 10 seconds, the share of display frames the compositor delivered late, free RAM and the page-in rate. Those samples run from 24 October, so they cover five days without the Governor and eight days with it.

The owner's account was that the worst periods (heavy input delay, sometimes a machine too slow to use) stopped once the Governor ran. The frame data agrees, and the change is large:

| Measure (share of 10-second samples, or count per day) | 24 to 28 Oct, no Governor | 30 Oct to 6 Nov, Governor running |
| --- | --- | --- |
| Samples with 20% or more of frames late | 1.3% to 14.3% (mean 6.0%) | 0.01% to 0.26% |
| Samples with 50% or more of frames late | 0.09% to 2.98% | 0% to 0.07% |
| Lag episodes logged by the monitor | 3 to 64 a day (148 in five days) | 0 to 1 a day (1 in eight days) |
| Samples above 20,000 page-ins/s | 1.8% to 6.7% | 1.3% to 8.5% |
| Median sessions running | 47 to 80 | 59 to 103 |

The first trims ran on 29 October at 17:11. On that day late-frame samples continued until 17:15, two more appeared near midnight, and then they almost stopped. The monitor's episode log goes back to 27 September and shows up to 161 episodes a day before 29 October, and 2 in total after it.

Three cautions apply.

- **Before-and-after is not a controlled test.** Other changes to the machine in the same week cannot be ruled out from these data. An earlier measurement on 29 October found late frames moving with another heavy workload's CPU use, not with free RAM.
- **Total paging did not fall.** The share of samples with heavy page-in rates was about the same before and after, while the fleet grew. If the Governor is the cause, it is not by reducing paging overall. One explanation that fits is timing: trimming idle sessions early and a few at a time may stop Windows from reclaiming memory from many processes at once, including the one in use. These data cannot test that.
- **Ten seconds is coarse.** Input delay happens in milliseconds. A 10-second sample shows how often frames were late, not how long a keystroke waited.

The frame data are the strongest evidence in this study that the Governor helps the person at the keyboard. They are also the least controlled.

## Reliability and design changes

The Governor halted itself twice in eight days, both times correctly, and each halt produced a permanent fix. Outside the two halts, the scheduled task missed 3 of its 5-minute slots after its run-lock fix on 2 November.

| Date | Event | Change that followed |
| --- | --- | --- |
| 7 Nov 01:18 | One slot lost: a sweep took 8.6 minutes to launch while free RAM was low. | None needed; launches were back under 1 second within 10 minutes. |
| 6 Nov 01:39 | Storm halt: a trimmed VS Code host carrying a second AI extension (Codex) used 6 CPU-seconds in 10.6 seconds. Halted 12.9 hours. | Hosts that parent a live Codex session are exempt, like those carrying Claude sessions. |
| 5 Nov 01:30 | A/B test of post-turn trims begins. | Odd hours: no post-turn trims. |
| 5 Nov 05:33, 05:53 | Two slots lost behind slow launches (282 s and 528 s). | None; within the 90-second lock wait design. |
| 2 Nov 01:49 | Storm halt: three extension hosts carrying Claude sessions faulted their memory back just before a burst of scheduled turns. Halted 10.4 hours. | Hosts that parent a live AI session are never trimmed. |
| 2 Nov 00:28 | Missed runs traced to the sweep and post-turn trims contending for the run lock. | Scheduled sweeps wait up to 90 seconds for the lock, and every lock miss is logged. |
| 1 Nov | Daylight-saving change: an ambiguous hour mislabelled. | Log stamps carry the real UTC offset; every run logs a START line and per-step timings. |
| 31 Oct | A freshly started extension host was trimmed during its own startup. | Young-process exemption (2 and 10 minutes); daily summary file. |
| 31 Oct | Stage 2: VS Code extension hosts join the candidates. | |
| 30 Oct 23:59 | Scheduled task live at stage 1 (sessions only). | |
| 29 Oct | Probe: one pass over 69 idle sessions took resident memory from 9,669 MB to 1,050 MB in 665 ms. It all regrew within about 40 minutes. | Trimming must repeat on a cadence; a one-off pass does not last. |

## Cost

The Governor costs about 1.5 CPU-seconds per run, which is roughly 4.5 billion clock cycles at the processor's 3.0 GHz base clock. Across a day that is 0.02 to 0.04 percent of the machine's processor capacity.

| Measure | Value |
| --- | --- |
| CPU time per sweep, measured on two dry runs on 7 Nov | 1.31 and 1.47 CPU-seconds (about half user, half kernel) |
| Wall time per sweep (daily medians) | 47 to 100 seconds, almost all of it the 10-second idle test and the 30-second watch, spent waiting |
| The trim calls themselves (daily medians) | 40 to 180 ms for 15 to 67 processes |
| Runs per day | 288 sweeps plus 100 to 460 post-turn trims |
| CPU per day | 10 to 19 CPU-minutes, about 1.8 to 3.4 trillion cycles at base clock |
| Share of capacity | 32 hardware threads give 2.76 million thread-seconds a day; the Governor uses 0.02 to 0.04 percent of them |

Most of that CPU time goes to starting PowerShell and querying the process list, not to trimming. A resident service would cost less, at the price of one more always-on process.

## Limits

Trimming buys RAM, not capacity, and it buys less as the machine gets fuller.

- **RAM, not commit.** A trimmed page still counts against the commit limit until the process frees it. On 7 November commit reached 94 to 97 percent of a 203 GB limit while the Governor ran normally. Only closing sessions lowers commit.
- **Diminishing returns under pressure.** On 7 November the machine's other work pushed free RAM toward 1 GB. Sweeps still released 400 to 500 MB of resident memory each, but the free RAM each one gained fell from a median of 264 MB overnight to 158 MB after 07:00. In a full system, other demand takes much of what a trim frees.
- **Regrowth.** By the next sweep 5 minutes later, the trimmed set had typically regrown 150 to 240 MB (daily medians). The benefit is a lower floor held by repetition, not a one-time saving.
- **Faulting back after a trim.** 6 to 16 percent of trimmed processes used CPU within 30 seconds of their trim (daily totals), so a trim sometimes pages straight back in. The idle test and the storm rule keep that small and catch it when it spreads.
- **Late launches under pressure.** Three scheduled slots were lost when a sweep took minutes to start.
- **Scope.** Windows only, judged by CPU idleness only. A window the user is about to click into can be trimmed; it pages back in on first use.

## Next: a controlled test of input delay

The before-and-after result is the one that matters most to a user, and it is the one this study controls least. A follow-up study is planned to test it directly.

- **Design.** Randomized crossover on the same machine and real workload. The Governor is switched on or off in 2-hour blocks, in random order, for at least 10 days. The first 40 minutes of each block are discarded, because trimmed memory takes about that long to regrow.
- **Measures, at millisecond resolution.** A scripted probe types into a foreground editor once a second and times each keystroke to the screen update. A frame-timing trace records the display. The operating system's per-process hard-fault counters show which processes were paging at each moment.
- **Outcome.** The 99th and 99.9th percentile of keystroke delay, and the number of seconds with a delay over 250 ms, in Governor-on blocks against Governor-off blocks, adjusted for the number of sessions running.
- **Why not a lab machine alone.** A synthetic bench can isolate the mechanism, but the stalls came from this workload. The crossover keeps the real workload and adds the control.

If the stalls return in Governor-off blocks and not in Governor-on blocks, the effect is causal for this machine. If they do not return, the change in late October had another cause.

## Conclusion

On a workstation running about a hundred AI coding sessions, trimming idle sessions every five minutes holds back a few hundred megabytes of RAM per sweep. It costs well under a tenth of a percent of the processor, and it did not cause the page-in bursts it was suspected of. It is a good default when idle sessions crowd a machine.

It cannot help once the commit limit is the constraint or the rest of the machine's work fills RAM. In those cases fewer sessions, not better trimming, is the fix.

The two halts showed that a self-stopping design matters more than a clever idle test. Both times, the process that faulted back was a VS Code host carrying live AI sessions, and both times the fix was to exempt it.

## Data and availability

- **Period:** 24 October to 7 November 2026, 09:45 Eastern. The display comparison uses 24 October onward; the Governor analysis covers 31 October onward, after the scheduled task went live.
- **Primary data:** the Governor's own run log, one line per run, 3,800 runs with a trim. Daily figures are medians or sums over those lines.
- **Page-in comparisons:** an independent validator's 10-second samples of the system page-in rate, read against the run log each day.
- **Display stalls:** a separate monitor's 10-second samples of late frames, free RAM and page-ins from 24 October, and its lag-episode log from 27 September.
- **Cost:** two dry runs on 7 November, measured with the operating system's per-process CPU counters.
- **Code:** this folder, [ramgovern](https://github.com/thealignedfew/skillgarden/tree/main/ramgovern), with its self-check and settings.
