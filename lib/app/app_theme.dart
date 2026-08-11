import 'package:fluent_ui/fluent_ui.dart';

final qingJuanAccent = AccentColor.swatch(const <String, Color>{
  'darkest': Color(0xFF603323),
  'darker': Color(0xFF83432F),
  'dark': Color(0xFFA9553D),
  'normal': Color(0xFFD16D50),
  'light': Color(0xFFDE886D),
  'lighter': Color(0xFFEAB09C),
  'lightest': Color(0xFFF8E5DD),
});

const qingJuanWarmOrange = Color(0xFFD19A64);
const qingJuanCoral = Color(0xFFD16D50);
const qingJuanPaper = Color(0xFFF4F0E6);
const qingJuanPaperSurface = Color(0xFFFFFDF8);
const qingJuanInk = Color(0xFF1B1A18);
const qingJuanDarkSurface = Color(0xFF24231F);
const qingJuanDarkElevated = Color(0xFF2C2A25);

FluentThemeData buildQingJuanTheme(Brightness brightness) {
  final isDark = brightness == Brightness.dark;
  return FluentThemeData(
    brightness: brightness,
    accentColor: qingJuanAccent,
    fasterAnimationDuration: const Duration(milliseconds: 60),
    fastAnimationDuration: const Duration(milliseconds: 110),
    mediumAnimationDuration: const Duration(milliseconds: 170),
    slowAnimationDuration: const Duration(milliseconds: 240),
    animationCurve: Curves.easeOutCubic,
    visualDensity: VisualDensity.standard,
    scaffoldBackgroundColor: isDark ? qingJuanInk : qingJuanPaper,
    micaBackgroundColor: isDark ? qingJuanInk : qingJuanPaper,
    acrylicBackgroundColor:
        isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
    menuColor: isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
    inactiveBackgroundColor:
        isDark ? const Color(0xFF34312B) : const Color(0xFFE8E1D4),
    cardColor: isDark ? qingJuanDarkSurface : qingJuanPaperSurface,
    navigationPaneTheme: NavigationPaneThemeData(
      animationDuration: const Duration(milliseconds: 110),
      animationCurve: Curves.easeOutCubic,
      backgroundColor: isDark ? qingJuanInk : qingJuanPaper,
      overlayBackgroundColor:
          isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
      headerPadding: const EdgeInsetsDirectional.only(
        start: 12,
        top: 14,
        end: 12,
        bottom: 6,
      ),
      iconPadding: const EdgeInsets.symmetric(horizontal: 12),
      labelPadding: const EdgeInsetsDirectional.only(end: 12),
    ),
    typography: Typography.raw(
      caption: TextStyle(
        fontSize: 12,
        color: isDark ? const Color(0xFFBDB6AA) : const Color(0xFF726B62),
      ),
      body: TextStyle(
        fontSize: 14,
        color: isDark ? const Color(0xFFF0ECE4) : const Color(0xFF35312C),
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        color: isDark ? const Color(0xFFF4F0E8) : const Color(0xFF302C27),
      ),
      subtitle: TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF5F1E9) : const Color(0xFF2D2925),
      ),
      title: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
      titleLarge: TextStyle(
        fontSize: 34,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
      display: TextStyle(
        fontSize: 42,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
    ),
  );
}
