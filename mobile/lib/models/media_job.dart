import 'package:uuid/uuid.dart';

enum JobStatus { queued, running, success, failed }

enum ToolType {
  downloader,
  trimCrop,
  compress,
  extractAudio,
  transform,
  gifCreator,
  bgEraser,
  hexPalette,
  imageEditor,
}

class MediaJob {
  MediaJob({
    String? jobId,
    required this.toolType,
    required this.inputPaths,
    required this.outputPath,
    required this.engineCommand,
    this.status = JobStatus.queued,
    this.progress = 0,
    this.errorLog,
    DateTime? createdAt,
  })  : jobId = jobId ?? const Uuid().v4(),
        createdAt = createdAt ?? DateTime.now().toUtc();

  final String jobId;
  final ToolType toolType;
  JobStatus status;
  double progress;
  final List<String> inputPaths;
  final String outputPath;
  final String engineCommand;
  String? errorLog;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => {
        'job_id': jobId,
        'tool_type': toolType.name,
        'status': status.name,
        'progress': progress,
        'input_paths': inputPaths,
        'output_path': outputPath,
        'engine_command': engineCommand,
        'error_log': errorLog,
        'created_at': createdAt.toIso8601String(),
      };

  factory MediaJob.fromJson(Map<String, dynamic> j) => MediaJob(
        jobId: j['job_id'] as String,
        toolType: ToolType.values.byName(j['tool_type'] as String),
        status: JobStatus.values.byName(j['status'] as String),
        inputPaths: List<String>.from(j['input_paths'] as List),
        outputPath: j['output_path'] as String,
        engineCommand: j['engine_command'] as String,
        errorLog: j['error_log'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      )..progress = (j['progress'] as num).toDouble();
}
