$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)
# GIL vs free-threaded CPython 3.14: where does CPU run out? (pure-Python CPU work in a 4-thread pool, 2-CPU container)
$g = 'aiohttp-gil,aiohttp-nogil,fastapi-gil,fastapi-nogil,django-gil,django-nogil'
python scripts/matrix.py --group gil --candidates $g --pass coarse --fast --tag p3 --endpoints pycpu --rates 10,15,20,25,30,40
python scripts/matrix.py --group gil --candidates aiohttp-gil,aiohttp-nogil,aiohttp-t-gilon --pass coarse --fast --tag p3 --endpoints pycpu --rates 10,20,30,40
python scripts/matrix.py --group gil --candidates $g --pass coarse --fast --tag p3 --endpoints cpu --rates 20,30,40,50
python scripts/matrix.py --group gil --candidates $g --pass coarse --fast --tag p3 --endpoints partner --rates 1000
python scripts/matrix.py --group gil --candidates $g --pass coarse --fast --tag p3 --endpoints payload --rates 2000
# Memory-heavy work (tag p4): every candidate does the same job per request. membuf = allocate+touch a 16 MiB buffer;
# memobj = build 50,000 small records (strings + int lists). Go, Java, aiohttp-Python, FastAPI, Django; 1 worker each, 2 CPUs / 512 MiB.
# Remove containers left over from any interrupted run first (the images were rebuilt with the new endpoints).
$old = docker ps -aq --filter name=^lb- ; if ($old) { docker rm -f $old | Out-Null }
python scripts/matrix.py --group mem --pass coarse --fast --tag p4 --endpoints membuf --rates 10,20,40
python scripts/matrix.py --group mem --pass coarse --fast --tag p4 --endpoints memobj --rates 10,20,40
