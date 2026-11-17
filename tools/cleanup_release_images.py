import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta


def api_pages(endpoint: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    pages = json.loads(result.stdout)
    if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
        raise ValueError(f"Unexpected paginated response from {endpoint}")
    return [item for page in pages for item in page]


def cleanup(repository: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name")

    releases = api_pages(f"repos/{repository}/releases?per_page=100")
    prereleases = [release for release in releases if release["prerelease"] and not release["draft"]]
    if not prereleases:
        print("No published prereleases found; nothing to clean up.")
        return

    prereleases.sort(
        key=lambda release: (
            datetime.fromisoformat(release["published_at"]),
            release["id"],
        ),
        reverse=True,
    )

    assets_by_release = [
        (release, api_pages(f"repos/{repository}/releases/{release['id']}/assets?per_page=100"))
        for release in prereleases
    ]
    newest, newest_assets = assets_by_release[0]
    if not any(asset["name"].endswith(".img.xz") for asset in newest_assets):
        raise RuntimeError(
            f"Newest prerelease {newest['tag_name']} has no .img.xz image; refusing cleanup."
        )

    cutoff = datetime.now(UTC) - timedelta(days=7)
    targets = [
        (release["tag_name"], asset["name"], asset["id"])
        for release, assets in assets_by_release[2:]
        if datetime.fromisoformat(release["published_at"]) <= cutoff
        for asset in assets
        if asset["name"].endswith(".img.xz") or asset["name"] == "SHA256SUMS"
    ]
    kept_tags = ", ".join(release["tag_name"] for release, _ in assets_by_release[:2])
    print(f"Keeping all assets for newest prereleases: {kept_tags}.", flush=True)
    print(f"Only removing images from releases published on or before {cutoff.isoformat()}.")
    for tag, name, asset_id in targets:
        if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id <= 0:
            raise ValueError(f"Invalid asset ID for {tag}: {name}")

    for tag, name, asset_id in targets:
        print(f"Deleting {tag}: {name}", flush=True)
        subprocess.run(
            ["gh", "api", "--method", "DELETE", f"repos/{repository}/releases/assets/{asset_id}"],
            check=True,
        )
    print(f"Deleted {len(targets)} asset(s).")


if __name__ == "__main__":
    cleanup(os.environ["GH_REPO"])
