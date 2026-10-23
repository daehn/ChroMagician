"""Validate, sign and archive the completed native .app for Apple Silicon."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def copy_build_bundle(source, destination):
    """Copy generated build files without inheriting Finder/File Provider metadata."""
    if source.is_symlink():
        destination.symlink_to(source.readlink())
    elif source.is_dir():
        destination.mkdir()
        for child in source.iterdir():
            copy_build_bundle(child, destination / child.name)
        destination.chmod(source.stat().st_mode & 0o777)
    else:
        shutil.copyfile(source, destination)
        destination.chmod(source.stat().st_mode & 0o777)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--identity', default='-', help='Developer ID Application identity, or - for local ad-hoc signing')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Signing inside synced Documents can race with metadata added by Finder.
    # Reconstruct this generated build in a local temporary folder, then sign
    # and archive the same bytes there. The original build remains untouched.
    with tempfile.TemporaryDirectory(prefix='chromagician-package-') as temporary:
        app = Path(temporary) / 'ChroMagician.app'
        copy_build_bundle(args.app.resolve(), app)
        package(app, output, args.identity)


def package(app, output, identity):
    macos = app / 'Contents/MacOS'
    for relative in ['chromatic_pc_backup', 'libexec/chromatic-backup', 'libexec/chromagician-update']:
        if not (macos / relative).is_file():
            raise RuntimeError('Incomplete Mac app: ' + relative)
    for tool in ['esptool', 'openFPGALoader']:
        if not (app / 'Contents/Resources/firmware/tools' / tool).is_file():
            raise RuntimeError('Incomplete Mac firmware tools: ' + tool)
    binaries = []
    # Finder/File Provider metadata is not allowed in signed bundles. Remove
    # only these packaging attributes; do not strip quarantine/security flags.
    for attribute in ('com.apple.FinderInfo', 'com.apple.ResourceFork'):
        run('/usr/bin/xattr', '-rd', attribute, str(app))
    for file in app.rglob('*'):
        if file.is_symlink() or not file.is_file():
            continue
        with file.open('rb') as stream:
            magic = stream.read(4)
        if magic not in [b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf']:
            continue
        architectures = run('lipo', '-archs', str(file)).split()
        if 'arm64' not in architectures:
            raise RuntimeError('Missing arm64 slice: ' + str(file))
        if architectures != ['arm64']:
            thin = file.with_name(file.name + '.arm64')
            run('lipo', str(file), '-thin', 'arm64', '-output', str(thin))
            thin.chmod(file.stat().st_mode & 0o777)
            thin.replace(file)
        for line in run('otool', '-L', str(file)).splitlines()[1:]:
            dependency = line.strip().split(' (')[0]
            if not dependency.startswith(('/usr/lib/', '/System/Library/', '@')):
                raise RuntimeError('External library in app: ' + dependency)
        binaries.append(file)
    signing = ['codesign', '--force', '--sign', identity]
    if identity != '-':
        signing += ['--options', 'runtime', '--timestamp']
    for file in binaries:
        if file != macos / 'chromatic_pc_backup':
            run(*signing, str(file))
    for framework in sorted(app.rglob('*.framework'), key=lambda p: len(p.parts), reverse=True):
        if not framework.is_symlink():
            run(*signing, str(framework))
    recipe = Path(__file__).resolve().parent
    run(*signing, '--entitlements', str(recipe.parent / 'macos/Runner/Release.entitlements'), str(app))
    run('codesign', '--verify', '--deep', '--strict', str(app))
    version = json.loads((app / 'Contents/Resources/version.json').read_text())['version']
    archive = output / f'ChroMagician-{version}-macos-arm64.tar.gz'
    # bsdtar preserves framework symlinks, executable modes and signed bundle contents.
    run('/usr/bin/tar', '-czf', str(archive), '-C', str(app.parent), app.name)
    sha = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    Path(str(archive) + '.sha256').write_text(f'{sha}  {archive.name}\n')
    repo = recipe.parent.parent
    revision = run('git', '-C', str(repo), 'rev-parse', 'HEAD')
    diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'])
    (output / 'macos-build-info.json').write_text(json.dumps({
        'source_commit': revision, 'working_tree_dirty': bool(run('git', '-C', str(repo), 'status', '--porcelain')),
        'tracked_diff_sha256': hashlib.sha256(diff).hexdigest(),
        'archive_sha256': sha, 'signing_identity': identity,
        'flutter': json.loads(run('flutter', '--version', '--machine')),
        'rustc': run('rustc', '--version'), 'xcode': run('xcodebuild', '-version'),
        'binaries': {str(p.relative_to(app)): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() for p in binaries},
    }, indent=2) + '\n')
    print('Validated and signed Apple Silicon app:', app.name)
    print('Release archive:', archive)


if __name__ == '__main__':
    main()
