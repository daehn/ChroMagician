"""Build a self-contained arm64 flashing-tool bundle. No device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(data, destination):
    if not destination.exists() or digest(destination) != data['sha256']:
        temporary = destination.with_suffix('.incoming')
        urllib.request.urlretrieve(data['url'], temporary)
        if digest(temporary) != data['sha256']:
            raise RuntimeError('Upstream download checksum mismatch')
        temporary.replace(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--downloads')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Build the macOS tools on Apple Silicon')
    recipe = Path(__file__).resolve().parent
    shared = json.loads((recipe / 'linux/inputs.json').read_text())
    inputs = {key: shared[key] for key in ('openFPGALoader', 'esptool_source')}
    inputs['libusb'] = json.loads((recipe / 'windows/inputs.json').read_text())['libusb']
    inputs.update(json.loads((recipe / 'macos/inputs.json').read_text()))
    output = Path(args.output).resolve()
    downloads = Path(args.downloads).resolve() if args.downloads else output.parent / 'macos-downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(Path(__file__).read_bytes() + json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    stamp = output / 'packaging.json'
    sources = output.parent / 'ChroMagician-macos-tools-sources.tar.gz'
    if stamp.exists() and sources.exists():
        saved = json.loads(stamp.read_text())
        if saved.get('key') == key and saved.get('source_sha256') == digest(sources) and all(
                (output / name).is_file() and digest(output / name) == sha for name, sha in saved['files'].items()):
            print('Verified cached macOS flashing tools.')
            return
    # New SDKs declare pipe2 even when targeting older macOS releases.
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET='12.0', ac_cv_func_pipe2='no')
    with tempfile.TemporaryDirectory(prefix='macos-tools-', dir=output.parent) as temporary:
        work = Path(temporary)
        for name, data in inputs.items():
            archive = downloads / name
            download(data, archive)
            with tarfile.open(archive) as source:
                source.extractall(work, filter='data')
        usb = work / ('libusb-' + inputs['libusb']['version'])
        prefix = work / 'deps'
        print(run(str(usb / 'configure'), '--prefix=' + str(prefix), '--disable-static',
                  '--enable-shared', cwd=usb, env=env))
        run('make', '-j2', cwd=usb, env=env)
        run('make', 'install', cwd=usb, env=env)
        source = work / ('openFPGALoader-' + inputs['openFPGALoader']['revision'])
        build = work / 'build'
        env['PKG_CONFIG_PATH'] = str(prefix / 'lib/pkgconfig')
        print(run('cmake', '-S', str(source), '-B', str(build),
                  '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_OSX_ARCHITECTURES=arm64',
                  '-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0', '-DENABLE_CABLE_ALL=OFF',
                  '-DENABLE_GOWIN_GWU2X=ON', '-DENABLE_USB_SCAN=ON',
                  '-DENABLE_VENDORS_ALL=OFF', '-DENABLE_GOWIN_SUPPORT=ON', env=env))
        run('cmake', '--build', str(build), '--parallel', '2', env=env)
        stage = work / 'firmware'
        tools = stage / 'tools'
        licenses = stage / 'licenses'
        tools.mkdir(parents=True)
        licenses.mkdir()
        shutil.copy2(build / 'openFPGALoader', tools / 'openFPGALoader')
        shutil.copy2(prefix / 'lib/libusb-1.0.0.dylib', tools / 'libusb-1.0.0.dylib')
        run('install_name_tool', '-change', str(prefix / 'lib/libusb-1.0.0.dylib'),
            '@loader_path/libusb-1.0.0.dylib', str(tools / 'openFPGALoader'))
        run('install_name_tool', '-id', '@loader_path/libusb-1.0.0.dylib', str(tools / 'libusb-1.0.0.dylib'))
        shutil.copy2(work / 'esptool-macos-arm64/esptool', tools / 'esptool')
        for name, license_path in [('openFPGALoader', source / 'LICENSE'),
                                   ('libusb', usb / 'COPYING'),
                                   ('esptool', work / 'esptool-macos-arm64/LICENSE')]:
            shutil.copy2(license_path, licenses / (name + '.txt'))
        imports = {}
        for binary in tools.iterdir():
            binary.chmod(0o755)
            if run('lipo', '-archs', str(binary)).strip() != 'arm64':
                raise RuntimeError('Non-arm64 tool: ' + binary.name)
            dependencies = [line.strip().split(' (')[0] for line in run('otool', '-L', str(binary)).splitlines()[1:]]
            if any(not dep.startswith(('/usr/lib/', '/System/Library/', '@loader_path/')) for dep in dependencies):
                raise RuntimeError('Unbundled dependency: ' + repr(dependencies))
            imports[binary.name] = dependencies
            run('codesign', '--force', '--sign', '-', str(binary))
        (stage / 'manifest.json').write_text(json.dumps({
            'schema_version': 1, 'portable_tools': True,
            'tools': {'esptool': ['tools/esptool'], 'openFPGALoader': ['tools/openFPGALoader']},
            'versions': inputs, 'libraries': [], 'macho_imports': imports,
        }, indent=2) + '\n')
        with tarfile.open(sources, 'w:gz') as archive:
            for name in inputs:
                archive.add(downloads / name, arcname='sources/' + name)
            for relative in ['package_macos_tools.py', 'macos/inputs.json', 'linux/inputs.json', 'windows/inputs.json']:
                archive.add(recipe / relative, arcname='recipe/' + relative)
        (stage / 'packaging.json').write_text(json.dumps({
            'key': key,
            'files': {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob('*')) if p.is_file()},
            'source_sha256': digest(sources),
        }, indent=2) + '\n')
        if output.exists():
            shutil.rmtree(output)
        stage.rename(output)
    print('Packaged macOS arm64 tools:', output)


if __name__ == '__main__':
    main()
