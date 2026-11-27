import 'package:flutter_test/flutter_test.dart';
import 'package:videl_mobile/core/update_checker.dart';

Map<String, dynamic> rel(String tag, {bool apk = true, bool prerelease = false}) => {
      'tag_name': tag,
      'draft': false,
      'prerelease': prerelease,
      'body': 'notes $tag',
      'assets': [
        if (apk) {'name': 'videl-android-arm64-v8a.apk', 'browser_download_url': 'https://x/$tag.apk'},
        {'name': 'Videl_Setup.exe', 'browser_download_url': 'https://x/$tag.exe'},
      ],
    };

void main() {
  test('an Android-only release reaches phones even though it is not "latest"', () {
    final info = newestApk([rel('android-5.3.3'), rel('v5.3.2'), rel('v5.3.1')], '5.3.2');
    expect(info?.latestVersion, '5.3.3');
    expect(info?.apkUrl, 'https://x/android-5.3.3.apk');
  });

  test('picks the highest version, whatever the order of the list', () {
    final info = newestApk([rel('v5.3.2'), rel('android-5.3.4'), rel('android-5.3.3')], '5.3.1');
    expect(info?.latestVersion, '5.3.4');
    expect(newestApk([rel('android-v5.3.5'), rel('v5.3.2')], '5.3.2')?.latestVersion, '5.3.5');
  });

  test('skips releases without an APK, prereleases and the android-latest build', () {
    expect(newestApk([rel('v5.4.0', apk: false), rel('v5.5.0', prerelease: true), rel('android-latest')], '5.3.2'), isNull);
    expect(newestApk([rel('v5.3.2'), rel('v5.3.1')], '5.3.2'), isNull);
  });
}
