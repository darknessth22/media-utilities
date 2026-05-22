import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_background_service_android/flutter_background_service_android.dart';

// Sticky foreground service so long FFmpeg jobs survive app backgrounding.
class VidelBackgroundService {
  static final _service = FlutterBackgroundService();

  static Future<void> init() async {
    await _service.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: _onStart,
        autoStart: false,
        isForegroundMode: true,
        notificationChannelId: 'videl_jobs',
        initialNotificationTitle: 'Videl',
        initialNotificationContent: 'Idle',
        foregroundServiceNotificationId: 1729,
        foregroundServiceTypes: [
          AndroidForegroundType.dataSync,
        ],
      ),
      iosConfiguration: IosConfiguration(autoStart: false),
    );
  }

  static Future<void> start() => _service.startService();
  static void stop() => _service.invoke('stopService');

  static void publishProgress(String jobId, double pct) {
    _service.invoke('progress', {'job_id': jobId, 'pct': pct});
  }
}

@pragma('vm:entry-point')
void _onStart(ServiceInstance service) {
  if (service is AndroidServiceInstance) {
    service.on('stopService').listen((_) => service.stopSelf());
  }
}
