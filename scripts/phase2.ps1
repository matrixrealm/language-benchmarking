$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)
# threads: virtual threads vs platform threads vs goroutines at thousands in flight
python scripts/matrix.py --group threads --pass coarse --fast --tag p2 --endpoints park --rates 250,1000,2000
python scripts/matrix.py --group threads --pass coarse --fast --tag p2 --endpoints fanout --rates 150,300
# core runtimes at higher traffic
python scripts/matrix.py --group core --pass coarse --fast --tag p2 --endpoints payload --rates 1500,2000
python scripts/matrix.py --group core --pass coarse --fast --tag p2 --endpoints cpu --rates 20,30,40
# python stacks
python scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints partner --rates 500,1000
python scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints payload --rates 1000,2000
python scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints cpu --rates 10,30
python scripts/matrix.py --group python --pass coarse --fast --tag p2 --endpoints fanout --rates 300
