import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;

import '../../core/theme/videl_theme.dart';

const _sendgridUrl = 'https://api.sendgrid.com/v3/mail/send';
const _senderEmail = 'videl.support@gmail.com';
const _recipientEmail = 'videl.support@gmail.com';

// Replaced at build time by CI — same token as the desktop build.
const _sendgridApiKey = String.fromEnvironment('SENDGRID_API_KEY', defaultValue: '');

const _bugTypes = ['UI Problem', 'Feature Problem', 'Crash / Error', 'Performance', 'Other'];

class BugReporterPage extends StatefulWidget {
  const BugReporterPage({super.key});

  @override
  State<BugReporterPage> createState() => _BugReporterPageState();
}

class _BugReporterPageState extends State<BugReporterPage> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();

  String _bugType = _bugTypes[0];
  String? _screenshotPath;
  bool _sending = false;
  String? _feedback;
  bool _feedbackError = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    _emailCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickScreenshot() async {
    final r = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'],
    );
    if (r == null) return;
    setState(() => _screenshotPath = r.files.single.path);
  }

  void _clearScreenshot() => setState(() => _screenshotPath = null);

  Future<void> _send() async {
    final title = _titleCtrl.text.trim();
    final desc = _descCtrl.text.trim();
    final email = _emailCtrl.text.trim();

    if (title.isEmpty) {
      setState(() {
        _feedback = 'Please enter a title.';
        _feedbackError = true;
      });
      return;
    }
    if (desc.isEmpty) {
      setState(() {
        _feedback = 'Please enter a description.';
        _feedbackError = true;
      });
      return;
    }

    if (_sendgridApiKey.isEmpty) {
      setState(() {
        _feedback = 'SENDGRID_API_KEY not configured in this build.';
        _feedbackError = true;
      });
      return;
    }

    setState(() {
      _sending = true;
      _feedback = 'Sending…';
      _feedbackError = false;
    });

    try {
      final subject = '[Videl Bug] $_bugType: $title';
      final body =
          'Bug Type: $_bugType\nReporter Email: ${email.isEmpty ? "(not provided)" : email}\n\n--- Description ---\n$desc';

      final toList = [
        {'email': _recipientEmail},
        if (email.isNotEmpty) {'email': email},
      ];

      final Map<String, dynamic> payload = {
        'personalizations': [
          {'to': toList}
        ],
        'from': {'email': _senderEmail, 'name': 'Videl Bug Reporter'},
        'subject': subject,
        'content': [
          {'type': 'text/plain', 'value': body}
        ],
      };

      if (_screenshotPath != null) {
        final file = File(_screenshotPath!);
        if (await file.exists()) {
          final bytes = await file.readAsBytes();
          final b64 = base64Encode(bytes);
          final ext = p.extension(_screenshotPath!).toLowerCase();
          final mime = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
          }[ext] ??
              'application/octet-stream';
          payload['attachments'] = [
            {
              'content': b64,
              'type': mime,
              'filename': p.basename(_screenshotPath!),
              'disposition': 'attachment',
            }
          ];
        }
      }

      final resp = await http
          .post(
            Uri.parse(_sendgridUrl),
            headers: {
              'Authorization': 'Bearer $_sendgridApiKey',
              'Content-Type': 'application/json',
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 30));

      if (resp.statusCode == 200 || resp.statusCode == 202) {
        _titleCtrl.clear();
        _descCtrl.clear();
        _emailCtrl.clear();
        setState(() {
          _bugType = _bugTypes[0];
          _screenshotPath = null;
          _feedback = 'Report sent successfully.';
          _feedbackError = false;
        });
      } else {
        setState(() {
          _feedback = 'SendGrid returned HTTP ${resp.statusCode}.';
          _feedbackError = true;
        });
      }
    } catch (e) {
      setState(() {
        _feedback = 'Failed to send: $e';
        _feedbackError = true;
      });
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Report a Bug')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            const Text(
              'Report a Bug',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            const Text(
              'Describe the issue and we\'ll look into it.',
              style: TextStyle(color: VidelColors.textSecondary, fontSize: 13),
            ),
            const SizedBox(height: 20),

            // Card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: VidelColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: VidelColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Bug type
                  _FieldLabel('Bug type'),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    value: _bugType,
                    dropdownColor: VidelColors.surface,
                    decoration: InputDecoration(
                      isDense: true,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: const BorderSide(color: VidelColors.border),
                      ),
                    ),
                    items: _bugTypes
                        .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                        .toList(),
                    onChanged: _sending
                        ? null
                        : (v) => setState(() => _bugType = v ?? _bugType),
                  ),
                  const SizedBox(height: 14),

                  // Title
                  _FieldLabel('Title'),
                  const SizedBox(height: 6),
                  TextFormField(
                    controller: _titleCtrl,
                    enabled: !_sending,
                    decoration: _inputDeco('Brief description of the issue'),
                  ),
                  const SizedBox(height: 14),

                  // Description
                  _FieldLabel('Description'),
                  const SizedBox(height: 6),
                  TextFormField(
                    controller: _descCtrl,
                    enabled: !_sending,
                    maxLines: 5,
                    decoration: _inputDeco('Steps to reproduce, expected vs actual…'),
                  ),
                  const SizedBox(height: 14),

                  // Screenshot
                  _FieldLabel('Screenshot (optional)'),
                  const SizedBox(height: 6),
                  Row(children: [
                    Expanded(
                      child: Text(
                        _screenshotPath == null
                            ? 'No screenshot selected'
                            : p.basename(_screenshotPath!),
                        style: const TextStyle(
                            color: VidelColors.textSecondary, fontSize: 12),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: _sending ? null : _pickScreenshot,
                      child: const Text('Browse'),
                    ),
                    if (_screenshotPath != null) ...[
                      const SizedBox(width: 8),
                      OutlinedButton(
                        onPressed: _sending ? null : _clearScreenshot,
                        child: const Text('Clear'),
                      ),
                    ],
                  ]),
                  if (_screenshotPath != null) ...[
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.file(
                        File(_screenshotPath!),
                        height: 120,
                        fit: BoxFit.cover,
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),

                  // Email
                  _FieldLabel('Your email (optional)'),
                  const SizedBox(height: 6),
                  TextFormField(
                    controller: _emailCtrl,
                    enabled: !_sending,
                    keyboardType: TextInputType.emailAddress,
                    decoration: _inputDeco('you@example.com'),
                  ),
                  const SizedBox(height: 18),

                  // Feedback
                  if (_feedback != null) ...[
                    Text(
                      _feedback!,
                      style: TextStyle(
                        fontSize: 12,
                        color: _feedbackError
                            ? const Color(0xFFF85149)
                            : const Color(0xFF3FB950),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],

                  // Send button
                  ElevatedButton(
                    onPressed: _sending ? null : _send,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    child: _sending
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Send Report',
                            style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputDeco(String hint) => InputDecoration(
        hintText: hint,
        hintStyle:
            const TextStyle(color: VidelColors.textMuted, fontSize: 13),
        isDense: true,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: VidelColors.border),
        ),
      );
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;
  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: VidelColors.textPrimary),
    );
  }
}
