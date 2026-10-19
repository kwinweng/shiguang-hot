"""Trigger the public workflow using the invoking machine's existing gh login."""
import argparse
import json
import subprocess
import sys
import time
import uuid

REPO = 'kwinweng/shiguang-hot'
WORKFLOW = 'hourly.yml'


def gh(*args, timeout=30):
    result = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'gh failed')
    return result.stdout


def emit(**values):
    print(json.dumps(values, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read workflow state without triggering it')
    parser.add_argument('--wait', action='store_true', help='Wait for a successful workflow conclusion')
    parser.add_argument('--timeout', type=int, default=300, help='Total seconds to find/wait for the run')
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    try:
        if args.check:
            workflow = json.loads(gh('api', f'repos/{REPO}/actions/workflows/{WORKFLOW}'))
            emit(status='read_access_ok', state=workflow['state'], url=workflow['html_url'],
                 actions_write='not_verified_by_read_check')
            if workflow['state'] != 'active':
                raise RuntimeError('The workflow is not active')
            return 0
        request_id = 'bot-' + uuid.uuid4().hex
        title = f'hourly / workflow_dispatch / {request_id}'
        deadline = time.monotonic() + args.timeout
        # Never retry a POST automatically: an uncertain response may already have queued a run.
        gh('workflow', 'run', WORKFLOW, '--repo', REPO, '--ref', 'main',
           '--field', f'dispatch_id={request_id}', timeout=min(30, args.timeout))
        emit(status='dispatch_accepted', dispatch_id=request_id)
        while time.monotonic() < deadline:
            runs = json.loads(gh('run', 'list', '--repo', REPO, '--workflow', WORKFLOW,
                                 '--branch', 'main', '--event', 'workflow_dispatch', '--limit', '50',
                                 '--json', 'databaseId,displayTitle,url,status,conclusion',
                                 timeout=max(1, min(30, deadline - time.monotonic()))))
            matches = [r for r in runs if r['displayTitle'] == title]
            if len(matches) > 1:
                raise RuntimeError(f'Multiple runs match {request_id}; inspect Actions before retrying')
            if matches:
                run = matches[0]
                emit(status='run_found', run_id=run['databaseId'], url=run['url'])
                if not args.wait:
                    emit(status='not_waited', note='The run was found; deployment success is not yet verified')
                    return 0
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                gh('run', 'watch', str(run['databaseId']), '--repo', REPO, '--exit-status',
                   timeout=remaining)
                final = json.loads(gh('run', 'view', str(run['databaseId']), '--repo', REPO,
                                      '--json', 'status,conclusion',
                                      timeout=max(1, min(30, deadline - time.monotonic()))))
                if final['status'] != 'completed' or final['conclusion'] != 'success':
                    raise RuntimeError(f"Workflow did not succeed: {final['status']} / {final['conclusion']}")
                emit(status='workflow_succeeded', run_id=run['databaseId'], url=run['url'])
                return 0
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        raise RuntimeError('Timed out confirming this dispatch; inspect Actions before retrying. The run was not canceled.')
    except (RuntimeError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as error:
        emit(status='error', message=str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main())
