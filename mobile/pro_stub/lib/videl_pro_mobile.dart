/// Videl Pro on Android: the public stand-in.
///
/// The app talks to Pro only through this API. Official builds replace this
/// package with the private one (the same API, with the license check, the
/// free daily runs and the License page) through pubspec_overrides.yaml:
///
///     dependency_overrides:
///       videl_pro_mobile:
///         path: ../videl_pro/mobile
///
/// A build from the public source has no Pro gate: every tool, batches
/// included, works without limits.
library videl_pro_mobile;

import 'package:flutter/widgets.dart';

/// True in official builds, false here.
const bool hasPro = false;

/// A Pro feature the free allowance does not cover; [message] says why.
class ProRequired implements Exception {
  ProRequired(this.message);
  final String message;
  @override
  String toString() => message;
}

class Pro {
  /// Load the license and start the background check-in.
  static Future<void> init({required String appVersion}) async {}

  /// Call before a Pro job; throws [ProRequired] when it is not covered, and
  /// counts one free run when it is. tool: "batch" (with [files]).
  static Future<void> gate(String tool, {int files = 1}) async {}

  /// "Pro: 3 of 5 free runs left today", or null when Pro is active.
  static Future<String?> freeRunsLabel() async => null;

  /// The License page, or null in builds without Pro.
  static Widget? licensePage() => null;
}
