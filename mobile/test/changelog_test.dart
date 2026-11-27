import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:videl_mobile/core/update_checker.dart' show kAppVersion;
import 'package:videl_mobile/features/whats_new/whats_new.dart';

// What's new is the only place the version shows, so the running version must
// have notes, and the list must stay newest first.
void main() {
  test('changelog has this version, newest first, with notes', () {
    final all = parseChangelog(File('assets/changelog.json').readAsStringSync());
    expect(all.first.version, kAppVersion);
    List<int> v(String s) => s.split('.').map(int.parse).toList();
    for (var i = 1; i < all.length; i++) {
      final a = v(all[i - 1].version), b = v(all[i].version);
      final newer = a[0] != b[0] ? a[0] > b[0] : a[1] != b[1] ? a[1] > b[1] : a[2] > b[2];
      expect(newer, isTrue, reason: '${all[i - 1].version} before ${all[i].version}');
    }
    for (final r in all) {
      expect(r.notes, isNotEmpty, reason: r.version);
    }
  });
}
