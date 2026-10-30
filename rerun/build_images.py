"""Build every benchmark image on a Linux host (the setup.ps1 equivalent) and pull k6.
The GIL study images use one pinned CPython patch: lb-gil = PYVER, lb-nogil = PYVER + 't'."""
import argparse, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]

def docker(*args): subprocess.run(['docker', *map(str, args)], check=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pyver', default='3.14.3', help='CPython patch used by both lb-gil and lb-nogil')
    a = p.parse_args()
    for d in ('python', 'java', 'go', 'fastapi', 'django'): docker('build', '-t', f'lb-{d}', ROOT / d)
    docker('build', '-t', 'lb-gil', '-f', ROOT / 'rerun' / 'Dockerfile.gil', '--build-arg', f'PYVER={a.pyver}', ROOT / 'gil')
    docker('build', '-t', 'lb-nogil', '-f', ROOT / 'rerun' / 'Dockerfile.gil', '--build-arg', f'PYVER={a.pyver}t', ROOT / 'gil')
    docker('pull', 'grafana/k6:1.3.0')

if __name__ == '__main__': main()
