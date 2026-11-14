"""Build only. No API runtime activation, scheduling or workflow execution."""
import argparse
import json
from pathlib import Path
from .compiler import compile_vault,canonical
from .repository import publish_release,_json_file


def main():
    parser=argparse.ArgumentParser(description='Compile a Git-pinned, reviewed knowledge release (does not activate the application)')
    parser.add_argument('--git-root',required=True)
    parser.add_argument('--vault',required=True)
    parser.add_argument('--approval',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source=Path(args.git_root).resolve()/args.vault
    if Path(args.output).resolve().is_relative_to(source.resolve()):parser.error('Artifacts must be outside source vault')
    manifest=compile_vault(args.git_root,args.vault,_json_file(Path(args.approval),16384))
    path=publish_release(args.output,manifest)
    print(json.dumps(dict(status='COMPILED_NOT_ACTIVATED',release_id=manifest['release_id'],manifest_sha256=manifest['manifest_sha256'],artifact=str(path))))


if __name__=='__main__':main()
