import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:chromatic_pc_backup/app_update.dart';
import 'package:chromatic_pc_backup/releases.dart';
import 'package:chromatic_pc_backup/update_install.dart';

void main() {
  late Directory root;
  setUp(() async {
    final temporary = await Directory.systemTemp.createTemp(
      'macos-update-test-',
    );
    root = Directory(await temporary.resolveSymbolicLinks());
  });
  tearDown(() async => root.delete(recursive: true));

  test('Mac bundle paths resolve helpers and version inside Contents', () async {
    final macos = await Directory(
      p.join(root.path, 'ChroMagician.app/Contents/MacOS'),
    ).create(recursive: true);
    final app = macos.parent.parent;
    final version = File(
      p.join(
        app.path,
        'Contents/Frameworks/App.framework/Resources/flutter_assets/version.json',
      ),
    );
    await version.create(recursive: true);
    await version.writeAsString('{"version":"1.2.3"}');
    expect(
      applicationDirectory(p.join(macos.path, 'chromatic_pc_backup')).path,
      app.path,
    );
    expect(bundleExecutable(app), 'Contents/MacOS/chromatic_pc_backup');
    expect(bundleHelper(app), 'Contents/MacOS/libexec/chromagician-update');
    expect(await bundleVersion(app), '1.2.3');
  });

  for (final extra in [
    ArchiveFile.string('ChroMagician.app/../../escape', 'bad'),
    ArchiveFile.symlink('ChroMagician.app/Contents/escape', '../../../outside'),
    ArchiveFile.symlink('ChroMagician.app/Contents/escape', '/tmp/outside'),
  ]) {
    test(
      'rejects unsafe Mac archive entry ${extra.name} ${extra.symbolicLink}',
      () async {
        final archive = Archive()..add(extra);
        final file = File(p.join(root.path, 'bad.tar.gz'));
        await file.writeAsBytes(gzip.encode(TarEncoder().encode(archive)));
        final stage = await Directory(p.join(root.path, 'stage')).create();
        await expectLater(
          extractAppUpdate(file.path, stage.path, '1.0.1', 'macos-arm64'),
          throwsA(isA<ReleaseFailure>()),
        );
        expect(await File(p.join(root.path, 'escape')).exists(), false);
      },
    );
  }
  test('rejects entries written through a framework symlink', () async {
    final archive = Archive()
      ..add(ArchiveFile.symlink('ChroMagician.app/link', 'Contents'))
      ..add(ArchiveFile.string('ChroMagician.app/link/payload', 'bad'));
    final file = File(p.join(root.path, 'bad.tar.gz'));
    await file.writeAsBytes(gzip.encode(TarEncoder().encode(archive)));
    final stage = await Directory(p.join(root.path, 'stage')).create();
    await expectLater(
      extractAppUpdate(file.path, stage.path, '1.0.1', 'macos-arm64'),
      throwsA(isA<ReleaseFailure>()),
    );
  });

  test(
    'Mac process identity uses live kernel start time and detects exit',
    () async {
      final identity = await processIdentity(pid);
      expect(identity, matches(RegExp(r'^\d+:\d+$')));
      expect(await processIdentity(pid), identity);
      final child = await Process.start('/bin/sleep', ['30']);
      final childIdentity = await processIdentity(child.pid);
      expect(childIdentity, isNotNull);
      child.kill();
      await child.exitCode;
      expect(await processIdentity(child.pid), isNull);
    },
    skip: !Platform.isMacOS,
  );

  test(
    'built Mac release extracts with valid signature and ARM64 helpers',
    () async {
      final archive = Platform.environment['CHROMAGIC_TEST_MACOS_ARCHIVE'];
      final version =
          Platform.environment['CHROMAGIC_TEST_MACOS_VERSION'] ?? '1.0.3';
      await extractAppUpdate(archive!, root.path, version, 'macos-arm64');
      expect(
        await bundleVersion(Directory(p.join(root.path, 'ChroMagician.app'))),
        version,
      );
    },
    skip:
        !Platform.isMacOS ||
        Platform.environment['CHROMAGIC_TEST_MACOS_ARCHIVE'] == null,
  );
}
