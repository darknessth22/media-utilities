import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// Exact palette from gui/theme.py (desktop dark mode).
class VidelColors {
  static const bg = Color(0xFF0A1020);          // root background
  static const sidebar = Color(0xFF0D1830);     // panels
  static const surface = Color(0xFF111C38);     // cards
  static const raised = Color(0xFF162040);      // inputs / chips
  static const border = Color(0xFF1B2F4C);      // dividers
  static const accent = Color(0xFF3B82F6);      // brand blue
  static const accentHover = Color(0xFF2563EB);
  static const accentPressed = Color(0xFF1D4ED8);
  static const textPrimary = Color(0xFFE6EDF3);
  static const textSecondary = Color(0xFF8B949E);
  static const textMuted = Color(0xFF484F58);
  static const success = Color(0xFF3FB950);
  static const error = Color(0xFFF85149);
  static const warning = Color(0xFFD29922);
}

// Subtle vertical gradient backdrop — matches desktop's layered dark feel.
const videlBackgroundGradient = LinearGradient(
  begin: Alignment.topCenter,
  end: Alignment.bottomCenter,
  colors: [VidelColors.sidebar, VidelColors.bg, Color(0xFF060B16)],
  stops: [0.0, 0.55, 1.0],
);

class VidelBackdrop extends StatelessWidget {
  const VidelBackdrop({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(gradient: videlBackgroundGradient),
      child: child,
    );
  }
}

ThemeData buildVidelTheme() {
  final base = ThemeData.dark(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    colorScheme: const ColorScheme.dark(
      surface: VidelColors.surface,
      surfaceContainerHighest: VidelColors.raised,
      primary: VidelColors.accent,
      secondary: VidelColors.accentHover,
      error: VidelColors.error,
      onSurface: VidelColors.textPrimary,
      onPrimary: Colors.white,
      outline: VidelColors.border,
    ),
    textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
      bodyColor: VidelColors.textPrimary,
      displayColor: VidelColors.textPrimary,
    ),
    cardTheme: CardThemeData(
      color: VidelColors.surface,
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 4),
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: VidelColors.border, width: 1),
        borderRadius: BorderRadius.circular(14),
      ),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: VidelColors.textPrimary,
      elevation: 0,
      centerTitle: false,
      surfaceTintColor: Colors.transparent,
    ),
    dividerTheme: const DividerThemeData(color: VidelColors.border, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: VidelColors.raised,
      hintStyle: const TextStyle(color: VidelColors.textMuted),
      labelStyle: const TextStyle(color: VidelColors.textSecondary),
      prefixIconColor: VidelColors.textSecondary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VidelColors.accent, width: 1.5),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: VidelColors.accent,
        foregroundColor: Colors.white,
        disabledBackgroundColor: VidelColors.border,
        disabledForegroundColor: VidelColors.textMuted,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: VidelColors.textPrimary,
        side: const BorderSide(color: VidelColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: VidelColors.accent,
      linearTrackColor: VidelColors.raised,
    ),
    tabBarTheme: const TabBarThemeData(
      labelColor: VidelColors.accent,
      unselectedLabelColor: VidelColors.textSecondary,
      indicatorColor: VidelColors.accent,
      dividerColor: Colors.transparent,
    ),
  );
}
