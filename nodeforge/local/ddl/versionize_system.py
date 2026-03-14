"""Embedded DDL constants for the versionize trigger system.

Carried directly from vm_wizard/docs/templates/sqlite/:
  - t_versionize_ddl.ddl
  - t_versionize_jobs.ddl
  - t_versionize_variables.ddl
  - trg_versionize_jobs.ddl (320 lines)
"""

T_VERSIONIZE_DDL = """
DROP TABLE IF EXISTS t_versionize_ddl;
CREATE TABLE t_versionize_ddl (
    table_name          TEXT NOT NULL,
    view_ddl            TEXT NOT NULL,
    trigger_insert_ddl  TEXT NOT NULL,
    trigger_update_ddl  TEXT NOT NULL,
    trigger_delete_ddl  TEXT NOT NULL,
    CONSTRAINT pk_t_versionize_ddl
        PRIMARY KEY (table_name)
);
"""

T_VERSIONIZE_JOBS = """
DROP TABLE IF EXISTS t_versionize_jobs;
CREATE TABLE t_versionize_jobs (
    table_name      TEXT,
    update_columns  TEXT,
    ignore_columns  TEXT
);
"""

T_VERSIONIZE_VARIABLES = """
DROP TABLE IF EXISTS t_versionize_variables;
CREATE TABLE t_versionize_variables (
    table_name          TEXT,
    calculation_ts      TEXT,
    insert_new_record   TEXT(1),
    has_update_only     TEXT(1),
    has_versioning      TEXT(1),
    CONSTRAINT pk_t_versionize_variables
        PRIMARY KEY (table_name)
);
"""

TRG_VERSIONIZE_JOBS = """
DROP TRIGGER IF EXISTS trg_versionize_jobs;
CREATE TRIGGER trg_versionize_jobs
AFTER INSERT ON t_versionize_jobs
BEGIN
    /* ----------------------------------------------------------------
       Gather the parameters of the just-inserted job
       ---------------------------------------------------------------- */
    INSERT INTO t_versionize_ddl(table_name,view_ddl,trigger_insert_ddl,trigger_update_ddl,trigger_delete_ddl)
	WITH indent AS (
		SELECT
			  '    ' AS one
			, '        ' AS two
			, '            ' AS three
			, '                ' AS four
	), params AS (
        SELECT
            NEW.table_name    AS tbl,
            COALESCE(NULLIF(TRIM(NEW.update_columns), ''), '') AS upd_cols,
            COALESCE(NULLIF(TRIM(NEW.ignore_columns), ''), '') AS ign_cols
	), all_columns AS (
		SELECT
			  name
			, CASE WHEN name IN ('version_valid_from','version_valid_to',
                           'version_changed_by','version_changed_at',
                           'version_is_deleted') THEN 1 ELSE 0 END AS is_version_field
			, CASE WHEN instr(','||params.ign_cols||',', ','||name||',') > 0 THEN 1 ELSE 0 END is_ignore_column
        FROM pragma_table_info((SELECT tbl FROM params))
		CROSS JOIN params
    ), pk_columns AS (
        SELECT name
        FROM pragma_table_info((SELECT tbl FROM params))
        WHERE pk > 0
          AND name NOT IN ('version_valid_from','version_valid_to',
                           'version_changed_by','version_changed_at',
                           'version_is_deleted')
    ), normal_columns AS (
        SELECT name
        FROM pragma_table_info((SELECT tbl FROM params)) ti
		CROSS JOIN params
        WHERE pk = 0
          AND ti.name NOT IN ('version_valid_from','version_valid_to',
                           'version_changed_by','version_changed_at',
                           'version_is_deleted')
          AND instr(','||params.upd_cols||',', ','||name||',') = 0
          AND instr(','||params.ign_cols||',', ','||name||',') = 0
    ), update_columns AS (
        SELECT name
        FROM pragma_table_info((SELECT tbl FROM params)) ti
		CROSS JOIN params
        WHERE pk = 0
          AND ti.name NOT IN ('version_valid_from','version_valid_to',
                           'version_changed_by','version_changed_at',
                           'version_is_deleted')
          AND instr(','||params.upd_cols||',', ','||name||',') > 0
    ), ignore_columns AS (
        SELECT name
        FROM pragma_table_info((SELECT tbl FROM params)) ti
		CROSS JOIN params
        WHERE pk = 0
          AND ti.name NOT IN ('version_valid_from','version_valid_to',
                           'version_changed_by','version_changed_at',
                           'version_is_deleted')
          AND instr(','||params.ign_cols||',', ','||name||',') > 0
    ), helper_strings AS (
		SELECT
			  pk_columns.pk_condition
			, pk_columns.pk_condition_TBL
			, all_columns.all_columns_list
			, all_columns_no_version_fields.all_columns_list_no_version_fields
			, all_columns_no_version_fields.all_columns_list_no_version_fields_NEW
			, all_columns_no_version_fields.all_columns_list_no_version_fields_NEW_tbl_for_ignore
			, all_columns_no_version_fields.all_columns_list_no_version_fields_NEW_COALESCE
			, COALESCE(normal_columns.normal_column_neq_condition,'') AS normal_column_neq_condition
			, COALESCE(normal_columns.normal_columns_list_NEW_COALESCE,'') AS normal_columns_list_NEW_COALESCE
			, COALESCE(update_columns.update_column_update,'') AS update_column_update
			, COALESCE(update_columns.update_column_neq_condition,'') AS update_column_neq_condition
			, COALESCE(update_columns.update_columns_list_NEW_COALESCE,'') AS update_columns_list_NEW_COALESCE
			, COALESCE(ignore_columns.ignore_columns_list_TBL,'') AS ignore_columns_list_TBL
		FROM
		(
			SELECT
				  GROUP_CONCAT(pk_columns.name || ' = NEW.' || pk_columns.name, char(10)||'AND ') AS pk_condition
				, GROUP_CONCAT('tbl.' || pk_columns.name || ' = NEW.' || pk_columns.name, char(10)||'AND ') AS pk_condition_TBL
			FROM pk_columns
		) pk_columns
		LEFT JOIN
		(
			SELECT
				  GROUP_CONCAT(all_columns.name, ',') AS all_columns_list
			FROM all_columns
		) all_columns
		ON 1=1
		LEFT JOIN
		(
			SELECT
				  GROUP_CONCAT(all_columns.name, char(10)||', ') AS all_columns_list_no_version_fields
				, GROUP_CONCAT('NEW.' || all_columns.name || ' AS ' || all_columns.name, char(10)||', ') AS all_columns_list_no_version_fields_NEW
				, GROUP_CONCAT(CASE WHEN is_ignore_column = 1 THEN 'tbl.' || all_columns.name ELSE 'NEW.' || all_columns.name || ' AS ' || all_columns.name END, char(10)||', ') AS all_columns_list_no_version_fields_NEW_tbl_for_ignore
				, GROUP_CONCAT('COALESCE(NEW.' || all_columns.name || ',tbl.' || all_columns.name || ') AS ' || all_columns.name, char(10)||', ') AS all_columns_list_no_version_fields_NEW_COALESCE
			FROM all_columns
			WHERE 1=1
			AND is_version_field = 0
		) all_columns_no_version_fields
		ON 1=1
		LEFT JOIN(
			SELECT
				  GROUP_CONCAT('COALESCE(latest.' || normal_columns.name || ','''') <> COALESCE(NEW.' || normal_columns.name|| ','''')', ' OR ') AS normal_column_neq_condition
				, GROUP_CONCAT('COALESCE(NEW.' || normal_columns.name || ',tbl.' || normal_columns.name || ') AS ' || normal_columns.name, char(10)||', ') AS normal_columns_list_NEW_COALESCE
			FROM normal_columns
		) normal_columns
		ON 1=1
		LEFT JOIN(
			SELECT
				  GROUP_CONCAT(update_columns.name || ' = NEW.' || update_columns.name, ','||char(10)) || ',' AS update_column_update
				, GROUP_CONCAT('COALESCE(latest.' || update_columns.name || ','''') <> COALESCE(NEW.' || update_columns.name ||','''')', ' OR ') AS update_column_neq_condition
				, GROUP_CONCAT('COALESCE(NEW.' || update_columns.name || ',tbl.' || update_columns.name || ') AS ' || update_columns.name, char(10)||', ') AS update_columns_list_NEW_COALESCE
			FROM update_columns
		) update_columns
		ON 1=1
		LEFT JOIN(
			SELECT
				  GROUP_CONCAT('tbl.' || ignore_columns.name, char(10)||', ') AS ignore_columns_list_TBL
			FROM ignore_columns
		) ignore_columns
		ON 1=1
	), view_sql AS (
		SELECT
            'CREATE VIEW vv'||SUBSTR(params.tbl,3)||char(10)||
            'AS'||char(10)||
			'SELECT'||char(10)||
			indent.one||helper_strings.all_columns_list_no_version_fields||char(10)||
			indent.one||', version_changed_by'||char(10)||
			'FROM '||params.tbl||char(10)||
            'WHERE 1=1'||char(10)||
			'AND version_is_deleted = ''N'''||char(10)||
            'AND version_valid_to = ''9999-12-31 00:00:00'';' AS sql_txt
        FROM params, helper_strings, indent
	), upsert_sql AS (
		SELECT
			indent.one||'/* 1. safe temporary variables to t_versionize_variables table. */'||char(10)||
			indent.one||'INSERT INTO t_versionize_variables (table_name,calculation_ts,insert_new_record,has_update_only,has_versioning)'||char(10)||
			indent.one||'SELECT'||char(10)||
			indent.two||'  insert_stmt.table_name'||char(10)||
			indent.two||', CURRENT_TIMESTAMP AS calculation_ts'||char(10)||
			indent.two||', CASE WHEN latest.version_valid_from IS NULL THEN ''Y'' ELSE ''N'' END AS insert_new_record'||char(10)||
			indent.two||', CASE WHEN ' || CASE WHEN helper_strings.update_column_neq_condition = '' THEN '1<>1' ELSE helper_strings.update_column_neq_condition END || ' THEN ''Y'' ELSE ''N'' END AS has_update_only'||char(10)||
			indent.two||', CASE WHEN ' || CASE WHEN helper_strings.normal_column_neq_condition = '' THEN '1<>1' ELSE helper_strings.normal_column_neq_condition END  || ' THEN ''Y'' ELSE ''N'' END AS has_versioning'||char(10)||
			indent.one||'FROM'||char(10)||
			indent.one||'('||char(10)||
			indent.two||'SELECT'||char(10)||
			indent.three||char(39)||params.tbl||char(39)|| ' AS table_name'||char(10)||
			indent.one||') insert_stmt'||char(10)||
			indent.one||'LEFT JOIN'||char(10)||
			indent.one||'('||char(10)||
            indent.two||'SELECT * FROM '||params.tbl||char(10)||
            indent.two||'WHERE '||helper_strings.pk_condition ||char(10)||
            indent.two||'AND version_valid_to = ''9999-12-31 00:00:00'''||char(10)||
            indent.two||'ORDER BY version_valid_from DESC LIMIT 1'||char(10)||
            indent.one||') latest'||char(10)||
			indent.one||'ON 1=1'||char(10)||
			indent.one||'WHERE true'||char(10)||
			indent.one||'ON CONFLICT(table_name) DO UPDATE SET '||char(10)||
			indent.two||'calculation_ts=excluded.calculation_ts,'||char(10)||
			indent.two||'insert_new_record=excluded.insert_new_record,'||char(10)||
			indent.two||'has_update_only=excluded.has_update_only,'||char(10)||
			indent.two||'has_versioning=excluded.has_versioning;'||char(10)||char(10)||
            indent.one||'/* 2. Insert new line, if primary key does not exist yet. */'||char(10)||
			indent.one||'INSERT INTO '||params.tbl||'('||helper_strings.all_columns_list|| ')'||char(10)||
			indent.one||'SELECT'||char(10)||
			indent.two||'  '||helper_strings.all_columns_list_no_version_fields||char(10)||
			indent.two||', controller.calculation_ts AS version_valid_from'||char(10)||
			indent.two||', ''9999-12-31 00:00:00'' AS version_valid_to'||char(10)||
			indent.two||', version_changed_by'||char(10)||
			indent.two||', controller.calculation_ts AS version_changed_at'||char(10)||
			indent.two||', ''N'' AS version_is_deleted'||char(10)||
			indent.one||'FROM'||char(10)||
			indent.one||'('||char(10)||
			indent.two||'SELECT'||char(10)||
			indent.three||'  '||helper_strings.all_columns_list_no_version_fields_NEW||char(10)||
			indent.three||', COALESCE(NEW.version_changed_by,''n/a'') AS version_changed_by'||char(10)||
			indent.one||') insert_stmt'||char(10)||
			indent.one||'INNER JOIN'||char(10)||
			indent.one||'('||char(10)||
            indent.two||'SELECT'||char(10)||
			indent.three||'  calculation_ts'||char(10)||
			indent.two||'FROM t_versionize_variables'||char(10)||
            indent.two||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.two||'AND insert_new_record = ''Y'''||char(10)||
            indent.one||') controller'||char(10)||
			indent.one||'ON 1=1;'||char(10)||char(10)||
			indent.one||'/* 3. Update current line update columns, if primary key does exist. */'||char(10)||
			indent.one||'UPDATE '||params.tbl||char(10)||
			indent.one||'SET ' || helper_strings.update_column_update ||char(10)||
			indent.two||'version_changed_by = COALESCE(NEW.version_changed_by,''n/a''),'||char(10)||
			indent.two||'version_changed_at = ('||char(10)||
			indent.three||'SELECT calculation_ts'||char(10)||
			indent.three||'FROM'||char(10)||
			indent.three||'('||char(10)||
			indent.four||'SELECT calculation_ts'||char(10)||
			indent.four||'FROM t_versionize_variables'||char(10)||
            indent.four||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.four||'AND insert_new_record = ''N'''||char(10)||
			indent.four||'AND has_update_only = ''Y'''||char(10)||
			indent.three||') controller'||char(10)||
			indent.two||')'||char(10)||
			indent.one||'WHERE EXISTS ('||char(10)||
            indent.two||'SELECT 1 FROM'||char(10)||
			indent.two||'('||char(10)||
			indent.three||'SELECT'||char(10)||
			indent.four||'  calculation_ts'||char(10)||
			indent.three||'FROM t_versionize_variables'||char(10)||
            indent.three||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.three||'AND insert_new_record = ''N'''||char(10)||
			indent.three||'AND has_update_only = ''Y'''||char(10)||
			indent.two||') controller'||char(10)||
            indent.one||')'||char(10)||
			indent.one||'AND '||helper_strings.pk_condition||char(10)||
			indent.one||'AND version_valid_to = ''9999-12-31 00:00:00'';'||char(10)||char(10)||
			indent.one||'/* 4. Update current line version fields, if primary key does exist. */'||char(10)||
			indent.one||'UPDATE '||params.tbl||char(10)||
			indent.one||'SET version_valid_to = ('||char(10)||
			indent.two||'SELECT calculation_ts'||char(10)||
			indent.two||'FROM'||char(10)||
			indent.two||'('||char(10)||
			indent.three||'SELECT calculation_ts'||char(10)||
			indent.three||'FROM t_versionize_variables'||char(10)||
            indent.three||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.three||'AND insert_new_record = ''N'''||char(10)||
			indent.three||'AND has_versioning = ''Y'''||char(10)||
			indent.two||') controller'||char(10)||
			indent.one||')'||char(10)||
			indent.one||'WHERE EXISTS ('||char(10)||
            indent.two||'SELECT 1 FROM'||char(10)||
			indent.two||'('||char(10)||
			indent.three||'SELECT'||char(10)||
			indent.four||'  calculation_ts'||char(10)||
			indent.three||'FROM t_versionize_variables'||char(10)||
            indent.three||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.three||'AND insert_new_record = ''N'''||char(10)||
			indent.three||'AND has_versioning = ''Y'''||char(10)||
			indent.two||') controller'||char(10)||
            indent.one||')'||char(10)||
			indent.one||'AND '||helper_strings.pk_condition ||';'||char(10)||char(10)||
			indent.one||'/* 5. Insert new line, if primary key does exist. */'||char(10)||
			indent.one||'INSERT INTO '||params.tbl||'('||helper_strings.all_columns_list|| ')'||char(10)||
			indent.one||'SELECT'||char(10)||
			indent.two||'  '||helper_strings.all_columns_list_no_version_fields||char(10)||
			indent.two||', controller.calculation_ts AS version_valid_from'||char(10)||
			indent.two||', ''9999-12-31 00:00:00'' AS version_valid_to'||char(10)||
			indent.two||', version_changed_by'||char(10)||
			indent.two||', controller.calculation_ts AS version_changed_at'||char(10)||
			indent.two||', ''N'' AS version_is_deleted'||char(10)||
			indent.one||'FROM'||char(10)||
			indent.one||'('||char(10)||
			indent.two||'SELECT'||char(10)||
			indent.three||'  '||helper_strings.all_columns_list_no_version_fields_NEW_tbl_for_ignore||char(10)||
			indent.three||', COALESCE(NEW.version_changed_by,''n/a'') AS version_changed_by'||char(10)||
			indent.two||'FROM '||params.tbl|| ' tbl'||char(10)||
			indent.two||'WHERE '||helper_strings.pk_condition_TBL ||char(10)||
            indent.two||'ORDER BY tbl.version_valid_from DESC LIMIT 1'||char(10)||
			indent.one||') insert_stmt'||char(10)||
			indent.one||'INNER JOIN'||char(10)||
			indent.one||'('||char(10)||
            indent.two||'SELECT'||char(10)||
			indent.three||'  calculation_ts'||char(10)||
			indent.two||'FROM t_versionize_variables'||char(10)||
            indent.two||'WHERE table_name = '||char(39)||params.tbl||char(39)||char(10)||
			indent.two||'AND insert_new_record = ''N'''||char(10)||
			indent.two||'AND has_versioning = ''Y'''||char(10)||
            indent.one||') controller'||char(10)||
			indent.one||'ON 1=1;'||char(10) AS sql_txt
        FROM params, helper_strings, indent
	), trigger_insert_sql AS (
		SELECT
            'CREATE TRIGGER trg_insert_vv'||SUBSTR(params.tbl,3)||
            ' INSTEAD OF INSERT ON vv'||SUBSTR(params.tbl,3)||char(10)||
            'BEGIN'||char(10)|| upsert_sql.sql_txt ||
            'END;' AS sql_txt
        FROM params, upsert_sql
	), trigger_update_sql AS (
		SELECT
            'CREATE TRIGGER trg_update_vv'||SUBSTR(params.tbl,3)||
            ' INSTEAD OF UPDATE ON vv'||SUBSTR(params.tbl,3)||char(10)||
            'BEGIN'||char(10)|| upsert_sql.sql_txt ||
            'END;' AS sql_txt
        FROM params, upsert_sql
	), trigger_delete_sql AS (
		SELECT
            'CREATE TRIGGER trg_delete_vv'||SUBSTR(params.tbl,3)||char(10)||
            'INSTEAD OF DELETE ON vv'||SUBSTR(params.tbl,3)||char(10)||
            'BEGIN'||char(10)||
            indent.one||'UPDATE '||params.tbl||' SET version_valid_to = CURRENT_TIMESTAMP,'||char(10)||
            indent.two||'version_changed_by = ''n/a'','||char(10)||
            indent.two||'version_changed_at = CURRENT_TIMESTAMP'||char(10)||
            indent.one||'WHERE '||REPLACE(helper_strings.pk_condition,'NEW','OLD')||char(10)||
			indent.one||'AND version_valid_to = ''9999-12-31 00:00:00'';'||char(10)||char(10)||
			indent.one||'INSERT INTO '||params.tbl||'('||helper_strings.all_columns_list|| ')'||char(10)||
            indent.one||'VALUES (OLD.'||REPLACE(helper_strings.all_columns_list_no_version_fields, ', ', ', OLD.')||char(10)||
			indent.two||', CURRENT_TIMESTAMP'||char(10)||
			indent.two||', ''9999-12-31 00:00:00'''||char(10)||
			indent.two||', ''n/a'''||char(10)||
			indent.two||', CURRENT_TIMESTAMP'||char(10)||
			indent.two||', ''Y'');'||char(10)||
            'END;' AS sql_txt
        FROM params, helper_strings, indent
	)
    SELECT
		  params.tbl
		, view_sql.sql_txt AS view_ddl
		, trigger_insert_sql.sql_txt AS trigger_insert_ddl
		, trigger_update_sql.sql_txt AS trigger_update_ddl
		, trigger_delete_sql.sql_txt AS trigger_delete_ddl
    FROM params, view_sql, trigger_insert_sql, trigger_update_sql, trigger_delete_sql
	WHERE 1=1
	ON CONFLICT(table_name) DO UPDATE SET
		view_ddl=excluded.view_ddl,
		trigger_insert_ddl=excluded.trigger_insert_ddl,
		trigger_update_ddl=excluded.trigger_update_ddl,
		trigger_delete_ddl=excluded.trigger_delete_ddl;
END;
"""

# Ordered list of DDLs to execute during DB initialization
VERSIONIZE_SYSTEM_DDLS = [
    T_VERSIONIZE_DDL,
    T_VERSIONIZE_JOBS,
    T_VERSIONIZE_VARIABLES,
    TRG_VERSIONIZE_JOBS,
]
