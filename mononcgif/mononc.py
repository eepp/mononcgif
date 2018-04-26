# Copyright (c) 2018 Philippe Proulx <eepp.ca>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
import os
import shutil
import subprocess
from functools import partial
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
import PyQt5.QtMultimedia as QtMultimedia
import PyQt5.QtMultimediaWidgets as QtMultimediaWidgets


def _error(msg):
    print('Error: {}'.format(msg), file=sys.stderr)
    sys.exit(1)


def _get_screen_geometries():
    desktop = QtWidgets.QApplication.desktop()
    screen_geos = []

    for i in range(desktop.screenCount()):
        screen_geos.append(desktop.screenGeometry(i))

    return screen_geos


class _CenterableWindow:
    def _center(self):
        desktop = QtWidgets.QApplication.desktop()
        geo = desktop.screenGeometry(desktop.primaryScreen())
        self.show()
        self.hide()
        self.move(geo.x() + geo.width() / 2 - (self.width() / 2),
                  geo.y() + geo.height() / 2 - (self.height() / 2))


class _QSelectRegionWindow(QtWidgets.QWidget):
    def __init__(self, screen_geo, region_accepted_func):
        super().__init__()
        self._region_accepted_func = region_accepted_func
        self.setWindowTitle('Capture')
        self._init_ui(screen_geo)
        self._create_overlay()
        self._init_pos = None
        self._cur_pos = None

    def _init_ui(self, screen_geo):
        self.setWindowFlags(QtCore.Qt.Widget |
                            QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint)
        self.setParent(None)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.move(screen_geo.x(), screen_geo.y())
        self.resize(screen_geo.width(), screen_geo.height())
        self.setCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.show()

    def _create_overlay(self):
        self._overlay = QtWidgets.QWidget()
        self._overlay.setStyleSheet('background-color: rgba(255, 0, 30, 50%);')
        self._overlay.setParent(self)

    def _update_overlay(self):
        self._overlay.move(self._init_pos.x(), self._init_pos.y())
        self._overlay.resize(self._cur_pos.x() - self._init_pos.x(),
                             self._cur_pos.y() - self._init_pos.y())

    def _close(self):
        self._overlay.close()
        del self._overlay
        self.close()

    def mousePressEvent(self, event):
        self._init_pos = event.pos()
        self._cur_pos = event.pos()
        self._update_overlay()
        self._overlay.show()

    def mouseReleaseEvent(self, event):
        self._cur_pos = event.pos()
        self._update_overlay()

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if pos.x() < self._init_pos.x() or pos.y() < self._init_pos.y():
            return

        self._cur_pos = pos
        self._update_overlay()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            _error('Cancelled by user')
            self._close()
        elif event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            if self._init_pos is None or self._cur_pos is None:
                return

            self._close()
            self._region_accepted_func(self._init_pos, self._cur_pos)
        else:
            super().keyPressEvent(event)


class _QSelectScreenWindow(QtWidgets.QWidget, _CenterableWindow):
    def __init__(self, screen_geo_selected_func):
        super().__init__()
        self._screen_geo_selected_func = screen_geo_selected_func
        screen_geos = _get_screen_geometries()

        if len(screen_geos) == 1:
            screen_geo_selected_func(screen_geos[0])
            self.close()
            return

        self.setWindowTitle('Select screen')
        self._init_ui()
        self._show_move()

    def _init_ui(self):
        vlayout = QtWidgets.QVBoxLayout()
        label = QtWidgets.QLabel('Select screen:')
        label.setStyleSheet('font-weight: bold;')
        vlayout.addWidget(label)
        hlayout = QtWidgets.QHBoxLayout()

        for screen_geo in _get_screen_geometries():
            text = '{}x{}'.format(screen_geo.width(),
                                  screen_geo.height())
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(partial(self._screen_geo_clicked,
                                           screen_geo))
            hlayout.addWidget(button)

        vlayout.addLayout(hlayout)
        self.setLayout(vlayout)
        self.layout().setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

    def _show_move(self):
        self._center()
        self.show()

    def _screen_geo_clicked(self, screen_geo):
        self.close()
        self._screen_geo_selected_func(screen_geo)


class _QCreateGifWindow(QtWidgets.QWidget, _CenterableWindow):
    def __init__(self, video_path, create_func):
        super().__init__()
        self._create_func = create_func
        self.setWindowTitle('Create GIF')
        self._init_multimedia(video_path)
        self._init_ui()
        self._show_move()

    def _init_multimedia(self, video_path):
        self._player = QtMultimedia.QMediaPlayer()
        self._w_video = QtMultimediaWidgets.QVideoWidget()
        self._player.setVideoOutput(self._w_video)
        self._playlist = QtMultimedia.QMediaPlaylist()
        url = QtCore.QUrl.fromLocalFile(video_path)
        self._playlist.addMedia(QtMultimedia.QMediaContent(url))
        self._playlist.setCurrentIndex(0)
        self._playlist.setPlaybackMode(QtMultimedia.QMediaPlaylist.CurrentItemInLoop)
        self._player.setPlaylist(self._playlist)
        self._player.pause()
        self._player.durationChanged.connect(self._duration_changed)

    def _init_ui(self):
        main_hlayout = QtWidgets.QHBoxLayout()

        # video side
        video_vlayout = QtWidgets.QVBoxLayout()
        top_labels_hlayout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel('Selected range: ')
        label.setStyleSheet('font-weight: bold;')
        top_labels_hlayout.addWidget(label)
        self._range_label = QtWidgets.QLabel('')
        top_labels_hlayout.addWidget(self._range_label)
        top_labels_hlayout.addStretch()
        video_vlayout.addLayout(top_labels_hlayout)
        video_vlayout.addWidget(self._w_video)
        self._slider_start = self._create_slider()
        self._slider_end = self._create_slider()
        video_vlayout.addWidget(self._slider_start)
        video_vlayout.addWidget(self._slider_end)
        layout = QtWidgets.QHBoxLayout()
        self._gif_width_edit = QtWidgets.QLineEdit('320')
        self._gif_width_edit.setPlaceholderText('GIF width')
        self._gif_width_edit.setToolTip('GIF width')
        layout.addWidget(self._gif_width_edit)
        layout.addStretch()
        video_vlayout.addLayout(layout)
        layout = QtWidgets.QHBoxLayout()
        self._gif_frame_rate_edit = QtWidgets.QLineEdit('10')
        self._gif_frame_rate_edit.setPlaceholderText('Frame rate')
        self._gif_frame_rate_edit.setToolTip('Frame rate')
        layout.addWidget(self._gif_frame_rate_edit)
        layout.addStretch()
        video_vlayout.addLayout(layout)
        layout = QtWidgets.QHBoxLayout()
        self._gif_colors_edit = QtWidgets.QLineEdit('128')
        self._gif_colors_edit.setPlaceholderText('Colors')
        self._gif_colors_edit.setToolTip('Colors')
        layout.addWidget(self._gif_colors_edit)
        layout.addStretch()
        video_vlayout.addLayout(layout)
        video_vlayout.addStretch()
        self._create_button = QtWidgets.QPushButton('Create')
        self._create_button.setDefault(True)
        layout = QtWidgets.QHBoxLayout()
        layout.addStretch()
        layout.addWidget(self._create_button)
        video_vlayout.addLayout(layout)
        main_hlayout.addLayout(video_vlayout)

        # GIF side
        gif_vlayout = QtWidgets.QVBoxLayout()
        top_labels_hlayout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel('GIF preview: ')
        label.setStyleSheet('font-weight: bold;')
        top_labels_hlayout.addWidget(label)
        self._gif_file_size_label = QtWidgets.QLabel('')
        top_labels_hlayout.addWidget(self._gif_file_size_label)
        top_labels_hlayout.addStretch()
        gif_vlayout.addLayout(top_labels_hlayout)
        self._gif_preview_label = QtWidgets.QLabel()
        gif_vlayout.addWidget(self._gif_preview_label)
        gif_vlayout.addStretch()
        main_hlayout.addLayout(gif_vlayout)

        # set my layout
        self.setLayout(main_hlayout)

        # connect signals
        self._create_button.clicked.connect(self._create_button_clicked)
        self._slider_start.valueChanged.connect(self._slider_start_value_changed)
        self._slider_end.valueChanged.connect(self._slider_end_value_changed)

    def _show_move(self):
        self.resize(600, 400)
        self._center()
        self.show()

    def _create_slider(self):
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setMinimum(0)
        slider.setSingleStep(100)
        slider.setPageStep(1000)
        return slider

    def _duration_changed(self, duration):
        duration -= 1
        self._start = 0
        self._end = duration
        self._slider_start.setMaximum(duration)
        self._slider_end.setMaximum(duration)
        self._slider_end.setValue(self._end)
        self._update_range_label()
        self._player.setPosition(0)
        self._player.pause()
        video_width = self._player.metaData('Resolution').width()
        self._gif_width_edit.setText(str(video_width))
        self._player.durationChanged.disconnect()

    def _update_range_label(self):
        self._range_label.setText('[{:.3f}, {:.3f}] s'.format(self._start / 1000,
                                                              self._end / 1000))

    def _slider_start_value_changed(self, value):
        self._player.setPosition(value)
        self._start = value

        if value > self._end:
            self._end = value
            self._slider_end.blockSignals(True)
            self._slider_end.setValue(value)
            self._slider_end.blockSignals(False)

        self._update_range_label()

    def _slider_end_value_changed(self, value):
        self._player.setPosition(value)
        self._end = value

        if value < self._start:
            self._start = value
            self._slider_start.blockSignals(True)
            self._slider_start.setValue(value)
            self._slider_start.blockSignals(False)

        self._update_range_label()

    def _create_button_clicked(self):
        self._create_func()

    def set_gif_preview(self, path):
        movie = QtGui.QMovie(path)
        self._gif_preview_label.setMovie(None)
        self._gif_preview_label.setMovie(movie)
        movie.start()
        size_text = '{:.3f} MiB'.format(os.stat(path).st_size / 1024 / 1024)
        self._gif_file_size_label.setText(size_text)

    @property
    def start(self):
        return self._start / 1000

    @property
    def end(self):
        return self._end / 1000

    @property
    def gif_width(self):
        return int(self._gif_width_edit.text())

    @property
    def gif_frame_rate(self):
        return int(self._gif_frame_rate_edit.text())

    @property
    def gif_colors(self):
        return int(self._gif_colors_edit.text())


class _App:
    _TMP_DIR = '/tmp/mononcgif-tmp'
    _CAPTURE_PATH = os.path.join(_TMP_DIR, 'out.ogv')
    _CAPTURE_MP4_PATH = os.path.join(_TMP_DIR, 'out.mp4')
    _PALETTE_PATH = os.path.join(_TMP_DIR, 'palette.png')
    _GIF_PATH = os.path.join(_TMP_DIR, 'out.gif')
    _OPTI_GIF_PATH = os.path.join(_TMP_DIR, 'out-opti.gif')

    def __init__(self, app):
        self._app = app
        self._user_gif_path = sys.argv[1]

    def run(self):
        self._select_screen_window = _QSelectScreenWindow(self._screen_geo_clicked)

    def _screen_geo_clicked(self, screen_geo):
        self._capture_window = _QSelectRegionWindow(screen_geo,
                                                    self._region_accepted)

    def _region_accepted(self, init_pos, cur_pos):
        x = init_pos.x()
        y = init_pos.y()
        width = cur_pos.x() - init_pos.x()
        height = cur_pos.y() - init_pos.y()
        self._capture_video(x, y, width, height)
        self._create_gif_window = _QCreateGifWindow(self._CAPTURE_PATH,
                                                    self._create_gif)

    def _capture_video(self, x, y, width, height):
        os.makedirs(self._TMP_DIR, exist_ok=True)
        res = subprocess.run([
            'recordmydesktop',
            '-x', str(x),
            '-y', str(y),
            '--width', str(width),
            '--height', str(height),
            '--no-cursor',
            '--no-sound',
            '--overwrite',
            '-o', self._CAPTURE_PATH,
        ])

        if res.returncode != 0:
            _error('recordmydesktop returned {}'.format(res.returncode))

    def _create_gif(self):
        total_time = self._create_gif_window.end - self._create_gif_window.start
        fps = self._create_gif_window.gif_frame_rate
        width = self._create_gif_window.gif_width
        res = subprocess.run([
            'ffmpeg',
            '-y',
            '-i', self._CAPTURE_PATH,
            self._CAPTURE_MP4_PATH,
        ])

        if res.returncode != 0:
            _error('ffmpeg returned {}'.format(res.returncode))

        res = subprocess.run([
            'ffmpeg',
            '-y',
            '-ss', str(self._create_gif_window.start),
            '-t', str(total_time),
            '-i', self._CAPTURE_MP4_PATH,
            '-vf', 'fps={},scale={}:-1:flags=lanczos,palettegen'.format(fps, width),
            self._PALETTE_PATH,
        ])

        if res.returncode != 0:
            _error('ffmpeg returned {}'.format(res.returncode))

        res = subprocess.run([
            'ffmpeg',
            '-y',
            '-ss', str(self._create_gif_window.start),
            '-t', str(total_time),
            '-i', self._CAPTURE_MP4_PATH,
            '-i', self._PALETTE_PATH,
            '-filter_complex', 'fps={},scale={}:-1:flags=lanczos[x];[x][1:v]paletteuse'.format(fps, width),
            self._GIF_PATH,
        ])

        if res.returncode != 0:
            _error('ffmpeg returned {}'.format(res.returncode))

        res = subprocess.run([
            'gifsicle',
            '-O3',
            '--colors', str(self._create_gif_window.gif_colors),
            self._GIF_PATH,
            '-o', self._OPTI_GIF_PATH,
        ])

        if res.returncode != 0:
            _error('gifsicle returned {}'.format(res.returncode))

        shutil.copy(self._OPTI_GIF_PATH, self._user_gif_path)
        self._create_gif_window.set_gif_preview(self._OPTI_GIF_PATH)


def run():
    qt_app = QtWidgets.QApplication(sys.argv[0:1])
    app = _App(qt_app)
    app.run()
    sys.exit(qt_app.exec_())
