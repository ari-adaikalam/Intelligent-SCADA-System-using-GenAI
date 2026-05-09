"""
SWAT Chart Generator
====================
Generates Chart.js configurations for data visualization.

Features:
- Line charts (time-series)
- Bar charts (comparisons)
- Auto-detection of chart type
- SCADA color scheme
- Responsive configurations

Dependencies: None (pure Python)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Generates Chart.js configurations for SWAT dashboard
    """
    
    def __init__(self):
        """Initialize chart generator with SCADA color scheme"""
        
        # SCADA color palette
        self.colors = {
            "primary": "rgb(33, 150, 243)",      # Blue
            "secondary": "rgb(0, 188, 212)",     # Cyan
            "success": "rgb(76, 175, 80)",       # Green
            "warning": "rgb(255, 152, 0)",       # Orange
            "danger": "rgb(244, 67, 54)",        # Red
            "info": "rgb(156, 39, 176)",         # Purple
            "gray": "rgb(158, 158, 158)",        # Gray
        }
        
        # Pump/sensor specific colors
        self.component_colors = [
            "rgb(33, 150, 243)",   # Blue
            "rgb(76, 175, 80)",    # Green
            "rgb(255, 152, 0)",    # Orange
            "rgb(244, 67, 54)",    # Red
            "rgb(156, 39, 176)",   # Purple
            "rgb(0, 188, 212)",    # Cyan
            "rgb(255, 193, 7)",    # Amber
            "rgb(103, 58, 183)",   # Deep Purple
        ]
    
    # ========================================================================
    # MAIN METHOD
    # ========================================================================
    
    def generate_chart(
        self,
        data: List[Dict[str, Any]],
        query_type: str = "show"
    ) -> Optional[Dict[str, Any]]:
        """
        Generate Chart.js configuration from query results
        
        Args:
            data: List of result rows (dictionaries)
            query_type: Type of query ("show", "compare", "analyze")
        
        Returns:
            Chart.js configuration dictionary or None
        """
        
        if not data or len(data) == 0:
            logger.info("[CHART] No data to visualize")
            return None
        
        try:
            logger.info(f"[CHART] Generating chart for {len(data)} rows")
            
            # Detect chart type based on data structure
            chart_type = self._detect_chart_type(data, query_type)
            
            logger.info(f"[CHART] Chart type: {chart_type}")
            
            # Generate appropriate chart configuration
            if chart_type == "line":
                config = self._generate_line_chart(data)
            elif chart_type == "bar":
                config = self._generate_bar_chart(data)
            elif chart_type == "pie":
                config = self._generate_pie_chart(data)
            else:
                # Default to line chart
                config = self._generate_line_chart(data)
            
            return config
            
        except Exception as e:
            logger.error(f"[CHART] Chart generation failed: {e}", exc_info=True)
            return None
    
    # ========================================================================
    # CHART TYPE DETECTION
    # ========================================================================
    
    def _detect_chart_type(
        self,
        data: List[Dict[str, Any]],
        query_type: str
    ) -> str:
        """
        Detect appropriate chart type based on data structure
        
        Intelligence:
        - Time-series data -> Line chart
        - Categorical comparisons -> Bar chart
        - Proportions/percentages -> Pie chart
        - Aggregated counts -> Bar chart
        - Trend analysis -> Line chart
        
        Returns: "line", "bar", or "pie"
        """
        
        if not data:
            return "line"
        
        first_row = data[0]
        columns = list(first_row.keys())
        num_rows = len(data)
        
        # Check if time-series data (has 'ts' or 'timestamp' column)
        has_time_column = any(col in columns for col in ['ts', 'timestamp', 'time', 'date'])
        
        if has_time_column:
            logger.info("[CHART] Detected time-series data -> LINE CHART")
            return "line"  # Time-series -> line chart
        
        # Check for categorical data (component names, status labels, etc.)
        categorical_cols = [
            col for col in columns
            if isinstance(first_row.get(col), str)
            and col not in ['id', 'plant_id', 'payload_json']
        ]
        
        # Check number of numeric columns
        numeric_cols = [
            col for col in columns 
            if col not in ['id', 'plant_id', 'payload_json', 'ts', 'timestamp']
            and isinstance(first_row.get(col), (int, float))
        ]
        
        # Detect proportions/percentages (pie chart)
        if len(numeric_cols) == 1 and num_rows <= 10 and len(categorical_cols) >= 1:
            # Single metric with categories -> Could be pie
            numeric_col = numeric_cols[0]
            if any(keyword in numeric_col.lower() for keyword in ['percent', 'proportion', 'ratio', 'count', 'total']):
                logger.info("[CHART] Detected proportional data -> PIE CHART")
                return "pie"
        
        # Detect comparisons (bar chart)
        if len(categorical_cols) >= 1 and len(numeric_cols) <= 3 and num_rows <= 20:
            # Comparing categories -> Bar chart
            logger.info("[CHART] Detected categorical comparison -> BAR CHART")
            return "bar"
        
        # Detect aggregated/grouped data
        if any(keyword in str(columns).lower() for keyword in ['count', 'sum', 'avg', 'average', 'total']):
            if num_rows <= 15:
                logger.info("[CHART] Detected aggregated data -> BAR CHART")
                return "bar"
        
        # Default scenarios
        if num_rows <= 10:
            logger.info(f"[CHART] Few data points ({num_rows}) -> BAR CHART")
            return "bar"
        
        if len(numeric_cols) > 3:
            logger.info(f"[CHART] Multiple metrics ({len(numeric_cols)}) -> LINE CHART")
            return "line"
        
        # Default to line chart for everything else
        logger.info("[CHART] Default -> LINE CHART")
        return "line"
    
    # ========================================================================
    # LINE CHART (Time-Series)
    # ========================================================================
    
    def _generate_line_chart(
        self,
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate line chart configuration for time-series data
        
        Suitable for: temperature trends, flow rates over time, etc.
        """
        
        # Extract time column (ts or timestamp)
        time_col = 'ts' if 'ts' in data[0] else 'timestamp' if 'timestamp' in data[0] else None
        
        if not time_col:
            # No time column, use index
            labels = [str(i) for i in range(len(data))]
        else:
            # Format timestamps
            labels = [self._format_timestamp(row[time_col]) for row in data]
        
        # Extract numeric columns (exclude id, plant_id, ts, payload_json)
        exclude_cols = ['id', 'plant_id', 'payload_json', 'ts', 'timestamp']
        numeric_cols = [
            col for col in data[0].keys()
            if col not in exclude_cols
            and isinstance(data[0].get(col), (int, float, type(None)))
        ]
        
        # Limit to 8 series (for readability)
        numeric_cols = numeric_cols[:8]
        
        # Build datasets
        datasets = []
        for i, col in enumerate(numeric_cols):
            # Extract values for this column
            values = [row.get(col) for row in data]
            
            # Determine color based on column name
            color = self._get_color_for_column(col, i)
            
            dataset = {
                "label": self._format_label(col),
                "data": values,
                "borderColor": color,
                "backgroundColor": self._add_alpha(color, 0.1),
                "borderWidth": 2,
                "tension": 0.4,  # Smooth curves
                "fill": False,
                "pointRadius": 2,
                "pointHoverRadius": 5
            }
            datasets.append(dataset)
        
        # Build Chart.js config
        config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {
                    "mode": "index",
                    "intersect": False
                },
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {
                            "color": "rgb(255, 255, 255)",
                            "usePointStyle": True,
                            "padding": 15
                        }
                    },
                    "tooltip": {
                        "enabled": True,
                        "backgroundColor": "rgba(0, 0, 0, 0.8)",
                        "titleColor": "rgb(255, 255, 255)",
                        "bodyColor": "rgb(255, 255, 255)",
                        "borderColor": "rgb(255, 255, 255)",
                        "borderWidth": 1
                    }
                },
                "scales": {
                    "x": {
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)"
                        },
                        "ticks": {
                            "color": "rgb(176, 176, 176)",
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    },
                    "y": {
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)"
                        },
                        "ticks": {
                            "color": "rgb(176, 176, 176)"
                        }
                    }
                }
            }
        }
        
        return config
    
    # ========================================================================
    # BAR CHART (Comparisons)
    # ========================================================================
    
    def _generate_bar_chart(
        self,
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate bar chart configuration for comparisons
        
        Suitable for: comparing values across components
        """
        
        # Get labels (usually component names or categories)
        exclude_cols = ['id', 'plant_id', 'payload_json', 'ts', 'timestamp']
        
        # Try to find a categorical column
        categorical_col = None
        for col in data[0].keys():
            if col not in exclude_cols and isinstance(data[0][col], str):
                categorical_col = col
                break
        
        if categorical_col:
            labels = [row[categorical_col] for row in data]
        else:
            labels = [f"Item {i+1}" for i in range(len(data))]
        
        # Get numeric columns
        numeric_cols = [
            col for col in data[0].keys()
            if col not in exclude_cols
            and col != categorical_col
            and isinstance(data[0].get(col), (int, float, type(None)))
        ]
        
        # Limit to 5 series for bar chart
        numeric_cols = numeric_cols[:5]
        
        # Build datasets
        datasets = []
        for i, col in enumerate(numeric_cols):
            values = [row.get(col) for row in data]
            color = self.component_colors[i % len(self.component_colors)]
            
            dataset = {
                "label": self._format_label(col),
                "data": values,
                "backgroundColor": self._add_alpha(color, 0.7),
                "borderColor": color,
                "borderWidth": 2
            }
            datasets.append(dataset)
        
        config = {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {
                            "color": "rgb(255, 255, 255)"
                        }
                    }
                },
                "scales": {
                    "x": {
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)"
                        },
                        "ticks": {
                            "color": "rgb(176, 176, 176)"
                        }
                    },
                    "y": {
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)"
                        },
                        "ticks": {
                            "color": "rgb(176, 176, 176)"
                        },
                        "beginAtZero": True
                    }
                }
            }
        }
        
        return config
    
    # ========================================================================
    # PIE CHART (Proportions)
    # ========================================================================
    
    def _generate_pie_chart(
        self,
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate pie chart configuration for proportions
        
        Suitable for: status distribution, component breakdown
        """
        
        # Extract labels and values
        labels = []
        values = []
        
        for row in data[:8]:  # Limit to 8 slices
            # Find label and value columns
            for key, value in row.items():
                if key not in ['id', 'ts', 'timestamp', 'payload_json']:
                    if isinstance(value, str):
                        labels.append(value)
                    elif isinstance(value, (int, float)):
                        values.append(value)
        
        # Generate colors
        colors = [self.component_colors[i % len(self.component_colors)] for i in range(len(labels))]
        
        config = {
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": "rgb(30, 30, 30)",
                    "borderWidth": 2
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "right",
                        "labels": {
                            "color": "rgb(255, 255, 255)"
                        }
                    }
                }
            }
        }
        
        return config
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def _format_timestamp(self, ts: Any) -> str:
        """Format timestamp for chart labels"""
        
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.strftime("%H:%M:%S")
            except:
                return ts
        elif isinstance(ts, datetime):
            return ts.strftime("%H:%M:%S")
        else:
            return str(ts)
    
    def _format_label(self, col: str) -> str:
        """Format column name into readable label"""
        
        # Remove common prefixes
        col = col.replace('true_', '')
        col = col.replace('_motor_', ' ')
        col = col.replace('_', ' ')
        
        # Capitalize
        return col.title()
    
    def _get_color_for_column(self, col: str, index: int) -> str:
        """Get appropriate color for a column based on its name"""
        
        col_lower = col.lower()
        
        # Temperature -> Red/Orange
        if 'temp' in col_lower:
            return self.colors["danger"]
        
        # Vibration -> Orange
        if 'vibration' in col_lower or 'vib' in col_lower:
            return self.colors["warning"]
        
        # Current -> Blue
        if 'current' in col_lower:
            return self.colors["primary"]
        
        # Flow -> Cyan
        if 'fit' in col_lower or 'flow' in col_lower:
            return self.colors["secondary"]
        
        # Level -> Green
        if 'lit' in col_lower or 'level' in col_lower:
            return self.colors["success"]
        
        # Pressure -> Purple
        if 'pit' in col_lower or 'pressure' in col_lower:
            return self.colors["info"]
        
        # Default: cycle through component colors
        return self.component_colors[index % len(self.component_colors)]
    
    def _add_alpha(self, rgb_color: str, alpha: float) -> str:
        """Convert rgb(r,g,b) to rgba(r,g,b,a)"""
        
        if rgb_color.startswith('rgb('):
            return rgb_color.replace('rgb(', 'rgba(').replace(')', f', {alpha})')
        return rgb_color
