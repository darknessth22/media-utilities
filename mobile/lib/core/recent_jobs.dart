import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class RecentJob {
  RecentJob({
    this.id,
    required this.tool,
    required this.input,
    required this.output,
    required this.status,
    this.createdAt,
  });

  int? id;
  final String tool;
  final String input;
  final String output;
  final String status; // success | failed
  DateTime? createdAt;

  Map<String, dynamic> toMap() => {
        'tool': tool,
        'input': input,
        'output': output,
        'status': status,
        'created_at': (createdAt ?? DateTime.now()).millisecondsSinceEpoch,
      };

  static RecentJob fromMap(Map<String, dynamic> m) => RecentJob(
        id: m['id'] as int?,
        tool: m['tool'] as String,
        input: m['input'] as String,
        output: m['output'] as String,
        status: m['status'] as String,
        createdAt: DateTime.fromMillisecondsSinceEpoch(m['created_at'] as int),
      );
}

class RecentJobs {
  static Database? _db;

  static Future<Database> _open() async {
    if (_db != null) return _db!;
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'videl_jobs.db');
    _db = await openDatabase(path, version: 1, onCreate: (db, _) async {
      await db.execute('''
        CREATE TABLE jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tool TEXT NOT NULL,
          input TEXT NOT NULL,
          output TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at INTEGER NOT NULL
        )
      ''');
    });
    return _db!;
  }

  static const int _maxRows = 30;

  static Future<void> add(RecentJob j) async {
    final db = await _open();
    await db.insert('jobs', j.toMap());
    // Trim — keep newest 30 rows only.
    await db.rawDelete('''
      DELETE FROM jobs WHERE id NOT IN (
        SELECT id FROM jobs ORDER BY created_at DESC LIMIT $_maxRows
      )
    ''');
  }

  static Future<List<RecentJob>> all({int limit = 100}) async {
    final db = await _open();
    final rows = await db.query('jobs',
        orderBy: 'created_at DESC', limit: limit);
    return rows.map(RecentJob.fromMap).toList();
  }

  static Future<void> clear() async {
    final db = await _open();
    await db.delete('jobs');
  }
}
