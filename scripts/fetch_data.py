import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

FILES = {
    "Completeness_783.csv": "https://github.com/philshiu/Drosophila_brain_model/raw/main/Completeness_783.csv",
    "Connectivity_783.parquet": "https://github.com/philshiu/Drosophila_brain_model/raw/main/Connectivity_783.parquet",
    "neuron_annotations.tsv": "https://github.com/flyconnectome/flywire_annotations/raw/main/supplemental_files/Supplemental_file1_neuron_annotations.tsv",
}


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "moodfly"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                sys.stdout.write(f"\r  {dest.name}: {done / total:6.1%} of {total / 1e6:.0f} MB")
                sys.stdout.flush()
    tmp.rename(dest)
    print()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = RAW / name
        if dest.exists():
            print(f"  {name}: already present")
            continue
        download(url, dest)
    print(f"Done. Files in {RAW}")


if __name__ == "__main__":
    main()
