import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';

void main() {
  runApp(const AnosWelcomeApp());
}

class AnosWelcomeApp extends StatefulWidget {
  const AnosWelcomeApp({super.key});

  @override
  State<AnosWelcomeApp> createState() => _AnosWelcomeAppState();
}

class _AnosWelcomeAppState extends State<AnosWelcomeApp> {
  // Default fallback color until the system command fetches the real one
  Color _seedColor = const Color(0xFF6750A4);
  ThemeMode _themeMode = ThemeMode.dark;

  @override
  void initState() {
    super.initState();
    _fetchSystemMaterialColor();
  }

  /// Executes kde-material-you-colors in the background to fetch the active
  /// system color palette, parsing the hex outputs to seamlessly theme this app.
  Future<void> _fetchSystemMaterialColor() async {
    try {
      print('[AnOS] Fetching system Material You color...');
      final result = await Process.run('kde-material-you-colors',[]);
      final output = result.stdout.toString() + '\n' + result.stderr.toString();

      Color? parsedColor;

      // ATTEMPT 1: Capture the explicit Material 3 seed color from logs
      // Ex:[I] m3_scheme_utils: get_color_schemes: Best colors: 0:#1a1c22 1:#d0deea 2:#a38779
      final bestColorsMatch = RegExp(r'Best colors:.*?2:(#[A-Fa-f0-9]{6})').firstMatch(output);

      if (bestColorsMatch != null) {
        final hexStr = bestColorsMatch.group(1)!.substring(1);
        parsedColor = Color(int.parse('FF$hexStr', radix: 16));
      } else {
        // ATTEMPT 2: Fallback to capturing the generic palette grid hexes at the end of output
        final hexRegex = RegExp(r'#([A-Fa-f0-9]{6})');
        final matches = hexRegex.allMatches(output).toList();

        if (matches.length >= 3) {
          // Index 2 usually represents a vibrant primary accent in these outputs
          final hexStr = matches[2].group(1)!;
          parsedColor = Color(int.parse('FF$hexStr', radix: 16));
        } else if (matches.isNotEmpty) {
          final hexStr = matches.last.group(1)!;
          parsedColor = Color(int.parse('FF$hexStr', radix: 16));
        }
      }

      if (parsedColor != null) {
        print('[AnOS] System color applied: $parsedColor');
        setState(() {
          _seedColor = parsedColor!;
        });
      } else {
        print('[AnOS] No hex colors found in command output. Using fallback.');
      }
    } catch (e) {
      print('[AnOS] Failed to execute kde-material-you-colors: $e');
    }
  }

  /// Toggles both the Flutter app theme AND the KDE Plasma system theme
  void _toggleTheme() {
    setState(() {
      _themeMode = _themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    });

    final isDark = _themeMode == ThemeMode.dark;
    final targetScheme = isDark ? 'MaterialYouDark' : 'MaterialYouLight';
    final fallbackScheme = isDark ? 'BreezeDark' : 'BreezeLight';

    // Command tries to apply MaterialYou scheme first, falls back to standard Breeze if missing
    final cmd = 'plasma-apply-colorscheme $targetScheme || plasma-apply-colorscheme $fallbackScheme';

    print('[AnOS] Applying KDE Theme: $targetScheme...');
    Process.run('bash', ['-c', cmd]).then((res) {
      if (res.stderr.toString().isEmpty) {
        print('[AnOS] KDE Theme applied successfully.');
      } else {
        print('[AnOS] KDE Theme stderr: ${res.stderr}');
      }
    }).catchError((e) {
      print('[AnOS] Failed to apply KDE theme: $e');
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AnOS Welcome',
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: _seedColor,
        brightness: Brightness.light,
        fontFamily: 'Roboto',
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: _seedColor,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF10141D), // Deep slate specific to your brand
        fontFamily: 'Roboto',
      ),
      home: WelcomeWizard(
        themeMode: _themeMode,
        onToggleTheme: _toggleTheme,
      ),
    );
  }
}

class WelcomeWizard extends StatefulWidget {
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  const WelcomeWizard({
    super.key,
    required this.themeMode,
    required this.onToggleTheme,
  });

  @override
  State<WelcomeWizard> createState() => _WelcomeWizardState();
}

class _WelcomeWizardState extends State<WelcomeWizard> {
  final PageController _pageController = PageController();
  int _currentPage = 0;
  bool _isConfiguring = false;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  /// Runs the requested system configuration hooks silently in the background
  Future<void> _runSystemHooks() async {
    print('[AnOS] Starting background configuration...');

    // 1. Wayland / Fcitx5 Native Protocol Setup
    // Configures Plasma 6 to route input via Wayland rather than Qt/X11 modules.
    final waylandFixScript = '''
    # Set Fcitx5 as the Wayland virtual keyboard for the live environment
    kwriteconfig6 --notify --file kwinrc --group Wayland --key InputMethod "org.fcitx.Fcitx5.desktop"
    kwriteconfig6 --notify --file kwinrc --group Wayland --key VirtualKeyboardEnabled true
    qdbus org.kde.KWin /VirtualKeyboard org.kde.kwin.VirtualKeyboard.setEnabled true || true

    # Inject the setting into /etc/skel so the new user (after Calamares install) inherits it automatically
    sudo mkdir -p /etc/skel/.config
    sudo kwriteconfig6 --file /etc/skel/.config/kwinrc --group Wayland --key InputMethod "org.fcitx.Fcitx5.desktop"
    sudo kwriteconfig6 --file /etc/skel/.config/kwinrc --group Wayland --key VirtualKeyboardEnabled true

    # Restart Fcitx5 to apply changes
    killall fcitx5 || true
    fcitx5 -d &
    ''';

    Process.run('bash',['-c', waylandFixScript]).then((res) {
      if (res.stderr.toString().isNotEmpty) {
        print('[AnOS] Wayland fix stderr: ${res.stderr}');
      }
    });

    // 2. Bash / Zsh fcitx5 hook
    final bashScript = '''
    sudo systemctl enable --now fcitx5-lotus-server@\$(whoami).service || \\
    (sudo systemd-sysusers && sudo systemctl enable --now fcitx5-lotus-server@\$(whoami).service)
    ''';
    Process.run('bash',['-c', bashScript]).then((res) {
      if (res.stderr.toString().isNotEmpty) print('[AnOS] Bash hook stderr: ${res.stderr}');
    });

    // 3. Fish fcitx5 hook
    final fishScript = '''
    sudo systemctl enable --now fcitx5-lotus-server@(whoami).service; or begin
    sudo systemd-sysusers; and sudo systemctl enable --now fcitx5-lotus-server@(whoami).service
    end
    ''';
    Process.run('fish', ['-c', fishScript]).then((res) {
      if (res.stderr.toString().isNotEmpty) print('[AnOS] Fish hook stderr: ${res.stderr}');
    }).catchError((_) {
      print('[AnOS] Fish not found, skipping fish hook.');
    });

    // 4. KDE Material You Colors Autostart
    final autostartScript = '''
    sudo bash -c 'cat <<EOF > /etc/xdg/autostart/kde-material-you-colors.desktop
[Desktop Entry]
Type=Application
Name=KDE Material You Colors
Exec=kde-material-you-colors
Icon=preferences-desktop-color
Terminal=false
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF'
    ''';
    Process.run('bash', ['-c', autostartScript]).then((res) {
      if (res.stderr.toString().isEmpty) {
        print('[AnOS] KDE autostart configured successfully.');
      } else {
        print('[AnOS] KDE autostart stderr: ${res.stderr}');
      }
    });

    // Artificial delay to show the configuration loading screen
    await Future.delayed(const Duration(milliseconds: 2000));
  }

  void _nextPage() async {
    if (_currentPage == 0) {
      setState(() => _isConfiguring = true);
      _pageController.animateToPage(
        1,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOutCubic,
      );

      await _runSystemHooks();

      if (mounted) {
        setState(() => _isConfiguring = false);
        _pageController.animateToPage(
          2,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeOutCubic,
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = widget.themeMode == ThemeMode.dark;

    return Scaffold(
      body: Stack(
        children:[
          PageView(
            controller: _pageController,
            physics: const NeverScrollableScrollPhysics(),
            onPageChanged: (int page) => setState(() => _currentPage = page),
            children:[
              _buildWelcomePage(),
              _buildConfigurationPage(),
              _buildFinalPage(),
            ],
          ),

          // Theme Toggle Button (Top Right)
          Positioned(
            top: 32,
            right: 32,
            child: IconButton.filledTonal(
              onPressed: widget.onToggleTheme,
              icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
              tooltip: 'Toggle Theme',
              padding: const EdgeInsets.all(12),
            ),
          ),

          // Navigation Footer
          if (_currentPage == 0)
            Positioned(
              bottom: 48,
              right: 48,
              child: FilledButton.icon(
                onPressed: _nextPage,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 20),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                icon: const Icon(Icons.arrow_forward),
                label: const Text('Bắt đầu (Next)', style: TextStyle(fontSize: 16)),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildWelcomePage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children:[
          const SizedBox(
            width: 180,
            height: 180,
            child: AnosLogo(),
          ),
          const SizedBox(height: 48),
          Text(
            'Chào mừng đến với AnOS',
            style: Theme.of(context).textTheme.displaySmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: Theme.of(context).colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Bản phân phối Linux tối ưu hóa cho người Việt.\nNhanh, đẹp và hoàn toàn tùy biến.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConfigurationPage() {
    return Center(
      child: Container(
        width: 450,
        padding: const EdgeInsets.all(48),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainer,
          borderRadius: BorderRadius.circular(28),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children:[
            SizedBox(
              width: 64,
              height: 64,
              child: CircularProgressIndicator(
                strokeWidth: 6,
                strokeCap: StrokeCap.round,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 48),
            Text(
              'Đang chuẩn bị hệ thống...',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Thiết lập bộ gõ tiếng Việt (Fcitx5 Lotus) và\nđồng bộ màu sắc giao diện Material You.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFinalPage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children:[
          Icon(
            Icons.check_circle_outline,
            size: 100,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 32),
          Text(
            'Mọi thứ đã sẵn sàng!',
            style: Theme.of(context).textTheme.displaySmall?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Bạn muốn làm gì tiếp theo?',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 64),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children:[
              OutlinedButton.icon(
                onPressed: () {
                  print('[AnOS] "Try AnOS" selected. Closing welcome app.');
                  exit(0);
                },
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                icon: const Icon(Icons.explore),
                label: const Text('Dùng thử (Try AnOS)', style: TextStyle(fontSize: 18)),
              ),
              const SizedBox(width: 24),
              FilledButton.icon(
                onPressed: () {
                  print('[AnOS] "Install AnOS" selected. Launching chimera-gui...');
                  Process.run('chimera-gui', []).then((_) {
                    print('[AnOS] chimera-gui launched successfully.');
                  }).catchError((e) {
                    print('[AnOS ERROR] Failed to run chimera-gui: $e');
                  }).whenComplete(() => exit(0));
                },
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                icon: const Icon(Icons.download),
                label: const Text('Cài đặt (Install AnOS)', style: TextStyle(fontSize: 18)),
              ),
            ],
          )
        ],
      ),
    );
  }
}

// ==========================================
// AnOS LOGO - MATERIAL YOU THEMED
// ==========================================

class AnosLogo extends StatelessWidget {
  const AnosLogo({super.key});

  @override
  Widget build(BuildContext context) {
    // Logo dynamically adopts the current Material 3 Theme colors
    final colorScheme = Theme.of(context).colorScheme;
    final backgroundColor = Theme.of(context).scaffoldBackgroundColor;

    return CustomPaint(
      painter: _AnosLogoPainter(
        primary: colorScheme.primary,
        tertiary: colorScheme.tertiary,
        background: backgroundColor,
      ),
    );
  }
}

class _AnosLogoPainter extends CustomPainter {
  final Color primary;
  final Color tertiary;
  final Color background;

  _AnosLogoPainter({
    required this.primary,
    required this.tertiary,
    required this.background,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width / 2;

    // 1. Draw Outer Star (Using system's Primary color)
    final outerPath = _createStarPath(
        outerRadius: maxRadius,
        innerRadius: maxRadius * 0.45,
        center: center);
    final primaryPaint = Paint()
      ..color = primary
      ..style = PaintingStyle.fill;

    // Drop shadow under the primary star for depth
    canvas.drawShadow(outerPath, Colors.black.withOpacity(0.3), 8, false);
    canvas.drawPath(outerPath, primaryPaint);

    // 2. Draw Inner Background Cutout (Uses Scaffold Background to create the gap effect)
    final cutoutPath = _createStarPath(
        outerRadius: maxRadius * 0.58,
        innerRadius: maxRadius * 0.25,
        center: center);
    final backgroundPaint = Paint()
      ..color = background
      ..style = PaintingStyle.fill;
    canvas.drawPath(cutoutPath, backgroundPaint);

    // 3. Draw Inner Accent Star (Using system's Tertiary accent color)
    final innerPath = _createStarPath(
        outerRadius: maxRadius * 0.48,
        innerRadius: maxRadius * 0.20,
        center: center);

    // Subtle gradient blending Primary and Tertiary for a rich Material finish
    final innerGradient = LinearGradient(
      colors:[tertiary.withOpacity(0.8), tertiary],
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
    ).createShader(Rect.fromCircle(center: center, radius: maxRadius * 0.48));

    final innerPaint = Paint()
      ..shader = innerGradient
      ..style = PaintingStyle.fill;

    canvas.drawPath(innerPath, innerPaint);
  }

  Path _createStarPath(
      {required double outerRadius, required double innerRadius, required Offset center}) {
    final path = Path();
    const int points = 5;
    const double step = (math.pi * 2) / points;

    path.moveTo(center.dx, center.dy - outerRadius);

    for (int i = 0; i < points; i++) {
      double outerAngle = step * i - (math.pi / 2);
      path.lineTo(
        center.dx + math.cos(outerAngle) * outerRadius,
        center.dy + math.sin(outerAngle) * outerRadius,
      );

      double innerAngle = outerAngle + (step / 2);
      path.lineTo(
        center.dx + math.cos(innerAngle) * innerRadius,
        center.dy + math.sin(innerAngle) * innerRadius,
      );
    }
    path.close();
    return path;
  }

  @override
  bool shouldRepaint(covariant _AnosLogoPainter oldDelegate) {
    return oldDelegate.primary != primary ||
        oldDelegate.tertiary != tertiary ||
        oldDelegate.background != background;
  }
}
