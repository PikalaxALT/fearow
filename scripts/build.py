#!/usr/bin/env python

import io
import pathlib
import subprocess
import tempfile
import zipfile

import requests

import fearow

if not (resp := fearow.needs_rebuild_db()):
    print("Nothing to do")
    exit()

print("Downloading PokeAPI ...")
zipball_resp = requests.get(
    resp["zipball_url"],
    headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
)
if zipball_resp.status_code != 200:
    print("Failed to download PokeAPI. Please build manually.")
    zipball_resp.raise_for_status()

zipdata = io.BytesIO(zipball_resp.content)
with tempfile.TemporaryDirectory() as tmpdir:
    zf = zipfile.ZipFile(zipdata)
    tldir = zf.filelist[0]
    zf.extractall(tmpdir)

    destdir = pathlib.Path(tmpdir) / zf.filelist[0].filename
    input(
        "Running 'make install'. This will install additional dependencies into your Python environment. Press Enter/Return to continue, CTRL+C to abort."
    )
    subprocess.run(["make", "-C", destdir, "install"], check=True)
    subprocess.run(["make", "-C", destdir, "setup"], check=True)
    subprocess.run(["make", "-C", destdir, "build-db"], check=True)

    built_db = pathlib.Path(destdir) / "db.sqlite3"
    built_db.rename(fearow.dbfile)
    print("Rebuilt databse!")
