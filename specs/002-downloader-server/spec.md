# Downloader server

Status: **not building a server** (decided 2026-11-18, after the test below). The web app's Downloader page hands links to the desktop app instead. A home laptop as the server, with daily limits, may be added later; the rest of this document is the plan and test record for that.

## Decision, 2026-11-18

- A rented server can't download YouTube or Facebook: both block datacenter addresses (test result below). The workarounds (account cookies, home-IP proxies, dodging the bot check, or asking visitors for their cookies) were rejected: against the sites' rules, banned accounts, proxy costs of thousands a month, and a login cookie opens a person's whole Google or Facebook account.
- Built instead: the Downloader page (`renderHandoff` in `web/js/main.js`) posts the link to the desktop app's browser bridge on 127.0.0.1:17654 (`core/extension_bridge.py` trusts `https://app.videl.app`). The app comes to the front with the link filled in and downloads on the visitor's own connection. Phones are pointed to the Android app. Needs a desktop release newer than 5.0.9.
- Possible later: the user's home laptop as the server, behind a Cloudflare Tunnel, with daily limits. Its home address passes YouTube, but every download crosses the home connection twice, and heavy use may make YouTube bot-check the user's own home address.
- Also priced and set aside: Cloudflare Containers (5 USD a month plus usage; not unlimited) and a Hetzner VPS (fixed price, 20 TB, but YouTube and Facebook blocked).

Related: [ARCHITECTURE.md](../../ARCHITECTURE.md) (bug relay and web app sections), [WORKFLOW.md](../../WORKFLOW.md) (web app, privacy-page rule), [LEARNINGS.md](../../LEARNINGS.md) (Android downloader and X/Spotify notes).

## Why it is needed

- The web app (https://app.videl.app) runs every tool in the browser, except the downloader: browsers are blocked from fetching media from YouTube, TikTok and similar sites. Its Downloader tile is a "coming soon" page (`nextTools` in `web/js/tools/index.js`).
- The desktop and Android apps download on the user's own device and do not need this server.
- So the server exists only to give the web app a downloader.

## What it does, per request

1. Accepts a link only from a supported site: YouTube (and YouTube Music), Facebook, Instagram, TikTok, X/Twitter, LinkedIn, Twitch, Spotify. Same allowlist as `_ALLOWED_PLATFORMS` in `core/downloader.py`.
2. Lists the available qualities, subtitles and playlist entries for the web app to show.
3. Downloads the chosen streams with yt-dlp, joining video and audio with FFmpeg without re-encoding.
4. Optionally: cuts a start and end time, converts audio to MP3, M4A, WAV, FLAC, OGG or Opus, adds subtitles, and tags songs with title, artist and cover.
5. Sends the finished file to the user's browser, then deletes it. Nothing is kept: no accounts, no database.
- Spotify works as on desktop and Android: the track list comes from Spotify's public embed page (`__NEXT_DATA__`) and each song is found on YouTube (`ytsearch1:Artist - Title`). Reuse the logic in `core/downloader.py` and `mobile/android/app/src/main/python/videl_dl.py`.

## Software

- Ubuntu 24.04.
- yt-dlp, updated daily (sites break it often; the desktop and Android builds also track the newest).
- FFmpeg.
- Deno: yt-dlp needs a JavaScript runtime for YouTube. TikTok's first-visit challenge is solved by recent yt-dlp in plain Python.
- A small Python web API (FastAPI) in front, reusing the desktop downloader code where it fits.
- HTTPS through Caddy, or through a Cloudflare Tunnel (free, no open ports, hides the server's IP).
- Address: `api.videl.app`. The videl.app zone is on the Cloudflare account (see the Cloudflare memory note), so DNS is one record.

## Built-in limits, to keep it cheap and safe

- At most 1080p and about 1 GB per file.
- No server-side video re-encoding. The desktop app re-encodes VP9/AV1 to H.264 for video editors (`_ensure_editor_compatible`), which is CPU-heavy; the server instead asks YouTube for its H.264 (avc1) formats, available up to 1080p. Users who need another format use the web app's Convert tool, which runs in their browser.
- Rate limit per visitor IP, and a small queue (1 or 2 downloads at once on minimum hardware).
- A daily bandwidth cap, with a clear "busy, try later or use the desktop app" message.
- Accept browser requests only from `https://app.videl.app` (CORS), like the bug relay's `WEB_ORIGINS`.
- Delete temporary files after sending, plus a timer that removes leftovers.

## Hardware

- Minimum: 1 vCPU, 1 GB RAM plus 2 GB swap, 15 to 20 GB SSD, about 1 TB of traffic a month, a public IPv4 address (required; IPv6-only plans fail on many sites). Handles 1 or 2 downloads at once.
- Comfortable: 2 vCPU, 4 GB RAM, 40 GB SSD, 2 TB or more of traffic. Roughly 5 to 10 downloads at once.
- Below the minimum is not worth it (for example Oracle's free Micro instance, 1/8 CPU and 1 GB).
- Per download: yt-dlp, FFmpeg and Deno together use about 150 to 250 MB of RAM.
- Server-side re-encoding would need about one core per job (4 to 8 vCPU), which is why it is ruled out.

## Traffic is the real cost

- Every download crosses the server twice: in from the site, out to the user. Most hosts bill only outgoing traffic.
- Example: 100 downloads a day at 200 MB is about 600 GB a month outgoing.

## Biggest risk: YouTube blocks datacenter IP addresses

- YouTube often answers server IPs with "Sign in to confirm you're not a bot". TikTok, Instagram and X are easier.
- Test before committing to any host: rent the smallest instance by the hour, run yt-dlp on a few YouTube, TikTok, Instagram and X links, and only then sign up for longer.
- If YouTube blocks it: cookies from a throwaway account, or a residential proxy for YouTube only (about 3 to 5 USD per GB).

### Test result: Hetzner Helsinki, 2026-11-18

Run with `tools/download_server/site_test.py` on a 1 vCPU / 1 GB server, yt-dlp 2026.11.17 nightly, Deno 2.9.8. The same links all worked from a home connection the same day.

- Worked over IPv4: TikTok, Instagram, X, LinkedIn, Twitch.
- YouTube and YouTube Music: "Sign in to confirm you're not a bot" on every direct link, over both IPv4 and IPv6. 0 of 20 look-ups in a row passed. One song found through a YouTube search (the Spotify path) did download, so the block is not absolute, but it is not usable.
- Facebook: "only available for registered users" for a video that works from home.
- IPv6 does not help: YouTube refuses it too, and TikTok, X and Twitch have no IPv6 addresses.
- Conclusion: a datacenter server can serve TikTok, Instagram, X, LinkedIn and Twitch, but not YouTube or Facebook without cookies or a proxy.

## Hosting options considered

Figures are from the planning research in November 2026; check current prices before buying.

- AWS (being tested now, see below).
- Cloudflare Containers. Figures from developers.cloudflare.com/containers/pricing, read 2026-11-18.
  - How: a Worker at `api.videl.app` in front of a container that runs yt-dlp, FFmpeg and Deno. A plain Worker cannot do the job: no Python, no FFmpeg binary, 128 MB memory.
  - Plan: needs Workers Paid (5 USD a month). That includes 25 GiB-hours of memory, 375 vCPU-minutes and 200 GB-hours of disk a month; after that it bills per 10 ms of running time.
  - Traffic: 1 TB outgoing a month is included in North America and Europe, then 0.025 USD per GB. Elsewhere it is 500 GB included, then 0.04 to 0.05 USD per GB.
  - Size: the `basic` instance (1/4 vCPU, 1 GiB, 4 GB disk) matches the minimum; `standard-1` (1/2 vCPU, 4 GiB, 8 GB) if YouTube's JavaScript challenge is too slow on it.
  - Advantages: it sleeps when idle, so it costs nothing between downloads. It is on the same account and zone as the sites, and there is no server to patch.
  - Downsides: above 1 TB a month it costs far more than Hetzner, which includes 20 TB. yt-dlp only stays fresh if the image is rebuilt (for example by a daily GitHub Action) or yt-dlp updates itself at container start.
  - Unknowns: the docs do not state the outgoing IPs (they are Cloudflare's, so YouTube may block them like any datacenter), the maximum run time, or the cold start time. Run the YouTube test on it first.
- Oracle Cloud A1 free tier: reportedly 2 OCPU and 12 GB now, 10 TB outgoing a month. Free, but capacity is often unavailable in popular regions.
- Hetzner CX23: about 5.49 EUR a month, 20 TB traffic. Can be rented by the hour, so it suits the YouTube test.
- Hostinger KVM 1: about 6.49 USD a month on a promotion, renewing at about 11.99, 4 TB. Avoid long prepaid terms.
- RackNerd deal plans: about 11 to 18 USD a year for 1 vCPU, 1 GB, 20 GB, 1 to 3 TB.
- Scaleway Stardust: avoid, because a public IPv4 costs extra (about 2.92 EUR a month).
- An old laptop at home, through a Cloudflare Tunnel:
  - Advantage: a home (residential) IP, which YouTube rarely blocks.
  - Costs: every download uses the home connection twice (download and upload), so upload speed and any monthly data quota decide whether it is viable. Needs caps on upload speed, simultaneous downloads (1 or 2) and daily volume.
  - Practical: Ubuntu Server, Ethernet, lid-close set to do nothing, battery charge limited if the BIOS allows it.

## AWS specifics (current test)

- Account: the new AWS experience, so the account is a "project". CLI profile `omniclouds`, Region `eu-north-1`. Signed in with `aws login --region eu-north-1 --profile omniclouds` (credentials last 12 hours, renew for 90 days). Details in the AWS memory note and in the AWS rules at the end of `CLAUDE.md`.
- Every Regional resource must be in eu-north-1. AWS App Runner is not available there.
- Candidate services:
  - Lightsail: a fixed monthly price that includes a data-transfer allowance, which suits a bandwidth-heavy server. There is a `deploying-containers-to-amazon-lightsail` skill.
  - EC2: flexible, but outgoing traffic is billed per GB above the free allowance, which can dominate the cost for a downloader.
  - ECS/Fargate: possible, but more moving parts than this needs.
- First check what the project allows: `aws freetier get-account-plan-state --profile omniclouds` (free or paid plan), and the project's spend limit in AWS Settings.
- Use the AWS skills (aws-compute, aws-containers, aws-billing-and-cost-management, deploying-containers-to-amazon-lightsail) for current prices and limits rather than memory.

## When it is built

- Wire the web app's Downloader page (`web/js/tools/index.js`, and a new tool module) to `https://api.videl.app`, then regenerate the search pages (`python tools/web_tool_pages.py`) if a downloader page is added there.
- Update `privacy.html` on gh-pages: a new service now sees the links people download and their IP address (WORKFLOW definition of done).
- Update ARCHITECTURE.md, WORKFLOW.md (how to deploy and update the server) and LEARNINGS.md.

## Open decisions

- Which host, after the YouTube test.
- The exact limits: maximum resolution, file size, downloads per IP per hour, daily bandwidth cap.
- Whether to offer playlists on the web, or single items only.
