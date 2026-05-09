"""
SWAT SQL Generator
==================
Generates and validates SQL queries for SCADA data retrieval.

Features:
- SQL generation using Mistral 7B
- Safety validation (prevents injection, only SELECT allowed)
- MS SQL execution with error handling
- Time range parsing

Dependencies: ollama, pyodbc
"""

import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available for SQL generation")

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logger.warning("pyodbc not available")


class SqlGenerator:
    """
    Generates and executes safe SQL queries for SWAT database
    """
    
    def __init__(self):
        """Initialize SQL generator"""
        self.table_name = "raw_plant_data"
        
        # SQL injection prevention patterns
        self.dangerous_keywords = [
            'insert', 'update', 'delete', 'drop', 'alter', 
            'truncate', 'create', 'exec', 'execute', 'xp_',
            'sp_', 'grant', 'revoke', 'deny', 'shutdown'
        ]
    
    # ========================================================================
    # MAIN METHOD
    # ========================================================================
    
    def generate_and_execute(
        self,
        message: str,
        intent: Dict,
        context: Dict,
        db_connection: Dict,
        ollama_model: str
    ) -> Dict[str, Any]:
        """
        Generate SQL from natural language, validate, and execute
        
        Returns:
        {
            "success": True,
            "sql": "SELECT ...",
            "data": [{...}, {...}],
            "row_count": 100
        }
        """
        
        try:
            logger.info("[SQL GEN] Generating SQL query...")
            
            # Parse time range from intent
            time_filter = self._parse_time_range(intent.get("time_range"), message)
            
            # Generate SQL using Mistral
            sql = self._generate_sql_with_mistral(
                message=message,
                intent=intent,
                context=context,
                time_filter=time_filter,
                ollama_model=ollama_model
            )
            
            if not sql:
                return {
                    "success": False,
                    "error": "Failed to generate SQL query"
                }
            
            logger.info(f"[SQL GEN] Generated SQL: {sql[:100]}...")
            
            # Validate SQL for safety
            is_safe, reason = self._validate_sql(sql)
            if not is_safe:
                logger.warning(f"[SQL GEN] Unsafe SQL rejected: {reason}")
                return {
                    "success": False,
                    "error": f"Query validation failed: {reason}"
                }
            
            logger.info("[SQL GEN] SQL validated, executing...")
            
            # Execute SQL
            results = self._execute_sql(sql, db_connection)
            
            return {
                "success": True,
                "sql": sql,
                "data": results,
                "row_count": len(results)
            }
            
        except Exception as e:
            logger.error(f"[SQL GEN] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ========================================================================
    # SQL GENERATION
    # ========================================================================
    
    def _generate_sql_with_mistral(
        self,
        message: str,
        intent: Dict,
        context: Dict,
        time_filter: Optional[str],
        ollama_model: str
    ) -> Optional[str]:
        """Generate SQL using Mistral 7B"""
        
        if not OLLAMA_AVAILABLE:
            logger.warning("Ollama not available, using template SQL")
            return self._template_sql(message, time_filter)
        
        try:
            # Build context for Mistral
            knowledge = "\n".join(context.get("knowledge", [])[:2])
            
            # Extract components mentioned
            components = intent.get("components", [])
            components_str = ", ".join(components) if components else "all relevant fields"
            
            prompt = f"""You are a SQL expert for a SCADA water treatment database.

Database Schema:
- Table: raw_plant_data
- Columns: id (int), ts (datetime2), plant_id (nvarchar), payload_json (nvarchar(MAX))

JSON Structure in payload_json:
{{
  "P101": 2, "P201": 2, ... (pump states: 0=OFF, 1=ON, 2=AUTO)
  "true_FIT101": 2.48, "true_FIT201": 2.45, ... (flow sensors)
  "true_LIT101": 503.13, "true_LIT301": 914.43, ... (level sensors)
  "true_PIT501": 247.22, ... (pressure sensors)
  "true_P101_motor_temp": 42.22, "true_P101_current": 2.55, "true_P101_vibration": 0.96
  ... (motor health for P101, P201, P203, P205, P302, P402, P403, P501)
}}

Extract JSON values using: JSON_VALUE(payload_json, '$.field_name')

User Question: "{message}"
Components mentioned: {components_str}
Time filter: {time_filter if time_filter else "Not specified"}

System Knowledge:
{knowledge}

CRITICAL RULE - COLUMN PRECISION:
SELECT ONLY the columns explicitly mentioned in the question.
- If question asks for "temperature", return ONLY temperature column(s)
- If question asks for "P101", return ONLY P101 data (not P201, P302, etc.)
- If question asks for "flow rate", return ONLY flow columns (not temp/pressure)
- If question asks for "P302 vibration", return ONLY P302 vibration (not current/temp)
- Do NOT add related columns unless explicitly requested
- Fetch all available data (Max 50000)
Examples of PRECISE column selection:
Q: "Show P101 temperature"
SQL: SELECT ts, CAST(JSON_VALUE(payload_json, '$.true_P101_motor_temp') AS FLOAT) AS P101_temp
     FROM raw_plant_data WHERE ... ORDER BY ts ASC

Q: "Show P302 vibration and current"
SQL: SELECT ts, 
     CAST(JSON_VALUE(payload_json, '$.true_P302_vibration') AS FLOAT) AS P302_vib,
     CAST(JSON_VALUE(payload_json, '$.true_P302_current') AS FLOAT) AS P302_curr
     FROM raw_plant_data WHERE ... ORDER BY ts ASC

Q: "Show FIT101 flow"
SQL: SELECT ts, CAST(JSON_VALUE(payload_json, '$.true_FIT101') AS FLOAT) AS FIT101
     FROM raw_plant_data WHERE ... ORDER BY ts ASC

Generate a SQL SELECT query that:
1. Uses ONLY the raw_plant_data table
2. Extracts ONLY explicitly mentioned JSON fields using JSON_VALUE
3. Filters by time: {time_filter if time_filter else "Get recent data (last 1000 rows)"}
4. Orders by ts ASC (oldest first) for time-series

IMPORTANT:
- Return ONLY the SQL query, no explanation
- Use JSON_VALUE for all payload fields
- Cast numeric fields: CAST(JSON_VALUE(...) AS FLOAT)
- MS SQL syntax only
- No comments in SQL
- BE PRECISE - only requested columns
- Fetch all data - (Max 2000)
Your SQL query:"""

            response = ollama.generate(
                model=ollama_model,
                prompt=prompt,
                options={"temperature": 0.1}  # Low temp for precise SQL
            )
            
            sql = response["response"].strip()
            
            # Clean up response (remove markdown, explanations)
            sql = self._clean_sql(sql)
            
            return sql
            
        except Exception as e:
            logger.error(f"Mistral SQL generation failed: {e}")
            return self._template_sql(message, time_filter)
    
    def _template_sql(self, message: str, time_filter: Optional[str]) -> str:
        """Fallback template-based SQL generation"""
        
        # Simple template for common queries
        message_lower = message.lower()
        
        # Default time filter
        if not time_filter:
            time_filter = "ts >= DATEADD(hour, -1, GETDATE())"
        
        # Temperature query
        if "temperature" in message_lower or "temp" in message_lower:
            return f"""
SELECT TOP 1000
  ts,
  CAST(JSON_VALUE(payload_json, '$.true_P101_motor_temp') AS FLOAT) AS P101_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P201_motor_temp') AS FLOAT) AS P201_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P203_motor_temp') AS FLOAT) AS P203_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P205_motor_temp') AS FLOAT) AS P205_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P302_motor_temp') AS FLOAT) AS P302_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P402_motor_temp') AS FLOAT) AS P402_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P403_motor_temp') AS FLOAT) AS P403_temp,
  CAST(JSON_VALUE(payload_json, '$.true_P501_motor_temp') AS FLOAT) AS P501_temp
FROM raw_plant_data
WHERE {time_filter}
ORDER BY ts ASC
"""
        
        # Flow query
        if "flow" in message_lower:
            return f"""
SELECT TOP 1000
  ts,
  CAST(JSON_VALUE(payload_json, '$.true_FIT101') AS FLOAT) AS FIT101,
  CAST(JSON_VALUE(payload_json, '$.true_FIT201') AS FLOAT) AS FIT201,
  CAST(JSON_VALUE(payload_json, '$.true_FIT301') AS FLOAT) AS FIT301,
  CAST(JSON_VALUE(payload_json, '$.true_FIT401') AS FLOAT) AS FIT401,
  CAST(JSON_VALUE(payload_json, '$.true_FIT501') AS FLOAT) AS FIT501
FROM raw_plant_data
WHERE {time_filter}
ORDER BY ts ASC
"""
        
        # Default: all sensor values
        return f"""
SELECT TOP 1000
  ts,
  plant_id,
  payload_json
FROM raw_plant_data
WHERE {time_filter}
ORDER BY ts DESC
"""

    # in sql_generator.py (inside class SqlGenerator)
    def _clean_sql(self, sql: str) -> str:
        original_sql = sql
        
        # Remove markdown code blocks
        sql = re.sub(r'```sql\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'```\s*', '', sql)

        # Remove comments - AGGRESSIVE
        # Remove C-style comments /* ... */ (non-greedy)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # Remove orphaned /* or */ that might remain
        sql = re.sub(r'/\*', '', sql)
        sql = re.sub(r'\*/', '', sql)
        
        # Remove SQL line comments --
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        
        # Remove any remaining forward slashes that aren't part of strings
        # This is a safety net to prevent the '/' syntax error
        sql = re.sub(r'\s*/\s*', ' ', sql)

        # Collapse whitespace
        sql = ' '.join(sql.split()).strip()

        # Remove a trailing semicolon (optional)
        sql = re.sub(r';\s*$', '', sql)
        
        # Log if significant cleaning occurred
        if len(original_sql) - len(sql) > 20:
            logger.info(f"[SQL CLEAN] Removed {len(original_sql) - len(sql)} characters (likely comments)")

        # --- Convert LIMIT/OFFSET to SQL Server ---
        # Supports:
        #   ... LIMIT 100
        #   ... LIMIT 100 OFFSET 0
        #   ... LIMIT 100 OFFSET 50
        # Updated: Now matches LIMIT anywhere in the query, not just at end
        m = re.search(r'\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?', sql, flags=re.IGNORECASE)
        if m:
            limit_n = int(m.group(1))
            offset_n = int(m.group(2)) if m.group(2) is not None else None

            # Remove the LIMIT/OFFSET clause (anywhere in query)
            sql = re.sub(r'\bLIMIT\s+\d+(?:\s+OFFSET\s+\d+)?', '', sql, flags=re.IGNORECASE).strip()

            if offset_n is None:
                # Prefer TOP when there's no offset
                if not re.match(r'^SELECT\s+TOP\s+\d+\s+', sql, flags=re.IGNORECASE):
                    sql = re.sub(r'^SELECT\s+', f'SELECT TOP {limit_n} ', sql, flags=re.IGNORECASE)
            else:
                # Use OFFSET/FETCH when there is an offset (SQL Server 2012+)
                # Ensure there is an ORDER BY (required for OFFSET/FETCH)
                if not re.search(r'\bORDER\s+BY\b', sql, flags=re.IGNORECASE):
                    sql += ' ORDER BY ts ASC'
                sql += f' OFFSET {offset_n} ROWS FETCH NEXT {limit_n} ROWS ONLY'

        return sql

    # ========================================================================
    # TIME RANGE PARSING
    # ========================================================================

    def _parse_time_range(self, time_range: Optional[Any], message: str) -> Optional[str]:
        """
        Parse time range from intent or message into SQL WHERE clause.
        Accepts: str | list[str] | None
        """

        # If intent gave a list (e.g., ["last hour", "today"]), pick one deterministically
        if isinstance(time_range, list):
            # pick the first non-empty string
            time_range = next((t for t in time_range if isinstance(t, str) and t.strip()), None)

        # If still not provided, try to extract from message text
        if not time_range:
            time_range = self._extract_time_from_message(message)

        if not time_range or not isinstance(time_range, str):
            return None

        time_range_lower = time_range.lower().replace(" ", "_")

        time_map = {
            "last_hour": "ts >= DATEADD(hour, -1, GETDATE())",
            "last_1_hour": "ts >= DATEADD(hour, -1, GETDATE())",
            "last_2_hours": "ts >= DATEADD(hour, -2, GETDATE())",
            "last_6_hours": "ts >= DATEADD(hour, -6, GETDATE())",
            "last_12_hours": "ts >= DATEADD(hour, -12, GETDATE())",
            "last_24_hours": "ts >= DATEADD(hour, -24, GETDATE())",
            "today": "ts >= CAST(CAST(GETDATE() AS DATE) AS DATETIME)",
            "yesterday": (
                "ts >= DATEADD(day, -1, CAST(CAST(GETDATE() AS DATE) AS DATETIME)) "
                "AND ts < CAST(CAST(GETDATE() AS DATE) AS DATETIME)"
            ),
            "this_week": "ts >= DATEADD(week, -1, GETDATE())",
            "last_week": "ts >= DATEADD(week, -2, GETDATE()) AND ts < DATEADD(week, -1, GETDATE())",
            "this_month": "ts >= DATEADD(month, -1, GETDATE())",
            "last_month": "ts >= DATEADD(month, -2, GETDATE()) AND ts < DATEADD(month, -1, GETDATE())",
        }

        return time_map.get(time_range_lower)

    def _extract_time_from_message(self, message: str) -> Optional[str]:
        """Extract time range from natural language message"""
        
        message_lower = message.lower()
        
        # Pattern matching
        patterns = {
            r'last\s+(\d+)\s+hour': lambda m: f"last_{m.group(1)}_hour",
            r'past\s+(\d+)\s+hour': lambda m: f"last_{m.group(1)}_hour",
            r'last\s+hour': lambda m: "last_hour",
            r'past\s+hour': lambda m: "last_hour",
            r'today': lambda m: "today",
            r'yesterday': lambda m: "yesterday",
            r'this\s+week': lambda m: "this_week",
            r'last\s+week': lambda m: "last_week",
            r'this\s+month': lambda m: "this_month",
            r'last\s+month': lambda m: "last_month"
        }
        
        for pattern, handler in patterns.items():
            match = re.search(pattern, message_lower)
            if match:
                return handler(match)
        
        return None
    
    # ========================================================================
    # SQL VALIDATION (SECURITY CRITICAL)
    # ========================================================================
    
    def _validate_sql(self, sql: str) -> tuple[bool, str]:
        """
        Validate SQL for safety
        
        Returns: (is_safe: bool, reason: str)
        """
        
        sql_lower = sql.lower().strip()
        
        # Must start with SELECT
        if not sql_lower.startswith('select'):
            return False, "Only SELECT queries are allowed"
        
        # Check for dangerous keywords
        for keyword in self.dangerous_keywords:
            if keyword in sql_lower:
                return False, f"Forbidden keyword detected: {keyword}"
        
        # Must reference raw_plant_data table
        if 'raw_plant_data' not in sql_lower:
            return False, "Query must use raw_plant_data table"
        
        # Prevent multiple statements (SQL injection attempt)
        if ';' in sql and not sql.rstrip().endswith(';'):
            return False, "Multiple statements not allowed"

        # Check for suspicious patterns
        suspicious_patterns = [
            r'union\s+select',  # UNION injection
            r'into\s+outfile',  # File operations
            r'load_file',       # File reading
            r'@@version',       # System variables
            r'xp_cmdshell',     # Command execution
            r'/\*(?!\*/)',      # Unclosed C-style comments
            r'\*/',             # Comment close without open
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, sql_lower):
                return False, f"Suspicious pattern detected: {pattern}"
        
        # Additional syntax checks
        # Check for unmatched parentheses
        if sql.count('(') != sql.count(')'):
            return False, "Unmatched parentheses in query"
        
        return True, "Valid"
    
    # ========================================================================
    # SQL EXECUTION
    # ========================================================================
    
    def _execute_sql(
        self, 
        sql: str, 
        db_connection: Dict
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results as list of dictionaries
        """
        
        if not PYODBC_AVAILABLE:
            raise Exception("pyodbc not available, cannot execute SQL")
        
        # Build connection string
        conn_str = self._build_connection_string(db_connection)
        
        connection = None
        cursor = None
        
        try:
            # Connect to database
            connection = pyodbc.connect(conn_str, timeout=10)
            cursor = connection.cursor()
            
            # Execute query with timeout
            cursor.execute(sql)
            
            # Fetch results
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Convert datetime to ISO string
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    row_dict[col] = value
                results.append(row_dict)
            
            logger.info(f"[SQL EXEC] Query returned {len(results)} rows")
            return results
            
        except pyodbc.Error as e:
            logger.error(f"[SQL EXEC] Database error: {e}")
            raise Exception(f"Database query failed: {str(e)}")
            
        finally:
            # Cleanup
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def _build_connection_string(self, db_connection: Dict) -> str:
        """Build MS SQL connection string from dictionary"""
        
        server = db_connection.get("server", "localhost")
        database = db_connection.get("database", "swat")
        username = db_connection.get("username")
        password = db_connection.get("password")
        
        if username and password:
            # SQL Server authentication
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
            )
        else:
            # Windows authentication
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )
        
        return conn_str
