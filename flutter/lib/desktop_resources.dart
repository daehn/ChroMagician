import 'dart:io';

import 'package:path/path.dart' as p;

String desktopResourcePath(String name, {String? executable, bool? isMacOS}) {
  final directory = p.dirname(executable ?? Platform.resolvedExecutable);
  return (isMacOS ?? Platform.isMacOS)
      ? p.normalize(p.join(directory, '..', 'Resources', name))
      : p.join(directory, name);
}
