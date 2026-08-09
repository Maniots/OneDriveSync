from PySide6.QtWidgets import QSizePolicy
from PySide6.QtGui import QFont
import pyqtgraph as pg
from pyqtgraph import PlotWidget, mkPen


class SyncChartWidget(PlotWidget):
    """
    A reusable chart widget for visualizing sync activity over time.
    Accepts data via set_data() method and displays a line chart with points.
    Designed for dark theme with minimal grid and modern appearance.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the chart appearance."""
        # Import theme colors
        from ..themes import colors

        # Dark background
        self.setBackground(colors.SURFACE)

        # Set axis styles
        axis_pen = mkPen(color=colors.BORDER, width=1)
        self.getAxis('left').setPen(axis_pen)
        self.getAxis('bottom').setPen(axis_pen)
        self.getAxis('left').setTextPen(colors.TEXT_SECONDARY)
        self.getAxis('bottom').setTextPen(colors.TEXT_SECONDARY)

        # Grid lines - subtle
        self.showGrid(x=True, y=True, alpha=0.15)

        # Enable antialiasing for smooth rendering
        self.setAntialiasing(True)

        # Set minimum size for visibility
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Initialize empty data line
        self._data_line = self.plot(
            pen=mkPen(colors.PRIMARY, width=2),
            symbol='o',
            symbolSize=6,
            symbolBrush=colors.PRIMARY,
            symbolPen=mkPen(colors.TEXT_PRIMARY, width=1)
        )

    def set_data(self, x, y):
        """
        Update the chart with new data.
        Args:
            x: List of x-values (typically time points)
            y: List of y-values (typically sync counts or similar)
        """
        if not x or not y or len(x) != len(y):
            # Clear data if invalid
            self._data_line.setData([], [])
            return

        self._data_line.setData(x, y)

    def clear_data(self):
        """Clear all data from the chart."""
        self._data_line.setData([], [])