/// Carer sign in: docs/design/screens/CarerLogin.dc.html.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/providers.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  // Pre-filled with the public demo account, as the design shows.
  final _email = TextEditingController(text: demoEmail);
  final _password = TextEditingController(text: demoPassword);
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).signIn(_email.text, _password.text);
    } catch (e) {
      final err = ApiError.from(e);
      setState(() => _error = err.status == 401 ? 'That email or password is wrong.' : err.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: PhoneFrame(
        child: LayoutBuilder(
          builder: (context, c) => SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 32),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: c.maxHeight - 64),
              child: IntrinsicHeight(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          width: 48,
                          height: 48,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(color: AppColors.primary, borderRadius: BorderRadius.circular(14)),
                          child: const Text(
                            'S',
                            style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700),
                          ),
                        ),
                        const DemoBadge(),
                      ],
                    ),
                    const SizedBox(height: 36),
                    Semantics(
                      header: true,
                      child: const Text(
                        'Welcome back',
                        style: TextStyle(fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: -0.6, height: 1.15),
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      "Sign in to see today's visits.",
                      style: TextStyle(fontSize: 15, color: AppColors.textMuted),
                    ),
                    const SizedBox(height: 24),
                    AutofillGroup(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _Field(
                            label: 'Email',
                            controller: _email,
                            keyboard: TextInputType.emailAddress,
                            autofill: AutofillHints.username,
                          ),
                          const SizedBox(height: 14),
                          _Field(
                            label: 'Password',
                            controller: _password,
                            obscure: true,
                            autofill: AutofillHints.password,
                            onSubmit: _submit,
                          ),
                        ],
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Semantics(
                        liveRegion: true,
                        child: Text(
                          _error!,
                          style: const TextStyle(color: AppColors.high, fontSize: 13, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(54)),
                      child: Text(_busy ? 'Signing in…' : 'Sign in'),
                    ),
                    const SizedBox(height: 24),
                    Panel(
                      radius: 20,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: const [
                          SectionTitle('Demo carer account', size: 13),
                          SizedBox(height: 8),
                          _Credential('Email', demoEmail),
                          SizedBox(height: 8),
                          _Credential('Password', demoPassword),
                        ],
                      ),
                    ),
                    const Spacer(),
                    const SizedBox(height: 24),
                    const Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(LucideIcons.smartphone, size: 18, color: AppColors.textSoft),
                        SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'No download needed. Use it in your browser, or choose “Add to Home Screen” for one-tap access.',
                            style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.textSoft),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class _Field extends StatelessWidget {
  const _Field({
    required this.label,
    required this.controller,
    this.keyboard,
    this.obscure = false,
    this.autofill,
    this.onSubmit,
  });
  final String label;
  final TextEditingController controller;
  final TextInputType? keyboard;
  final bool obscure;
  final String? autofill;
  final VoidCallback? onSubmit;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        keyboardType: keyboard,
        obscureText: obscure,
        autocorrect: false,
        autofillHints: autofill == null ? null : [autofill!],
        onSubmitted: onSubmit == null ? null : (_) => onSubmit!(),
        style: const TextStyle(fontSize: 15),
        decoration: InputDecoration(
          hintText: label,
          hintStyle: const TextStyle(color: AppColors.textMuted),
        ),
      ),
    ],
  );
}

class _Credential extends StatelessWidget {
  const _Credential(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisAlignment: MainAxisAlignment.spaceBetween,
    children: [
      Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
      Text(value, style: const TextStyle(fontSize: 13, fontFamily: 'monospace')),
    ],
  );
}
