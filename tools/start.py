"""Minimal dependency preflight before importing the existing production server."""
import sys
from ide_api.startup import check

def main():
    try:check()
    except ValueError as exc:raise SystemExit('Cannot start EMBODY: '+str(exc)) from None
    from ide_api.server import main as serve
    serve()

if __name__=='__main__':main()
