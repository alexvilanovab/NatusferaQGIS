# -*- coding: utf-8 -*-
from PyQt4.QtCore import QUrl, QCoreApplication, Qt, QThread, QObject, SIGNAL
from PyQt4.QtGui import QAction, QIcon, QFileDialog, QMessageBox, QDialog
from PyQt4 import uic
from qgis.core import QgsVectorLayer, QgsMapLayerRegistry
import resources, urllib2, os.path, unicodedata, re, csv
from urllib2 import HTTPError, URLError


BASE_FORM, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'natusfera_qgis_dialog_base.ui'))
class NatusferaQGISDialogBase(QDialog, BASE_FORM):
    def __init__(self, parent=None):
        # set up dialog
        super(NatusferaQGISDialogBase, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        self.setupUi(self)

    def closeEvent(self, event):
        # clean dialog
        self.username_line_edit.clear()
        self.username_line_edit.setFocus()
        self.project_line_edit.clear()
        self.species_line_edit.clear()
        # close dialog
        event.accept()


class DownloadingThread(QThread):
    def __init__(
        self, parent, csv_page, csv_totalpages, csv_dir, csv_corrected_dir,
        url):
        # set up thread
        QThread.__init__(self, parent)
        # set up variables
        self.parent = parent
        self.csv_page = csv_page
        self.csv_totalpages = csv_totalpages
        self.csv_dir = csv_dir
        self.csv_corrected_dir = csv_corrected_dir
        self.url = url
        self.csv_invalid_fields = []

    def run(self):
        # open csv files
        with open(self.csv_dir, 'w+') as csv_file, \
                open(self.csv_corrected_dir, 'w') as csv_corrected_file:
            # get csv headers
            csv_headers = urllib2.urlopen(
                self.url.format(1)).readline().replace('\n', '').split(',')
            # add them to both csv files
            csv_file.write(','.join(csv_headers) + '\n')
            csv_corrected_file.write(','.join(csv_headers) + '\n')
            # for each natusfera csv page
            for page in range(self.csv_page, self.csv_totalpages):
                # write csv lines excepting headers
                csv_file.writelines(
                    urllib2.urlopen(self.url.format(page)).readlines()[1:])
                # update download dialog
                self.emit(SIGNAL('update'))
            # set up csv writer
            csv_file.seek(0)
            csv_writer = csv.DictWriter(
                csv_corrected_file, fieldnames = csv_headers)
            # for each csv row
            for csv_row in csv.DictReader(csv_file):
                # if row has invalid latitude and/or invalid longitude
                if csv_row['Latitude'] == '' or csv_row['Longitude'] == '':
                    # add field to 'csv_invalid_fields' list
                    if csv_row['Scientific name'] != '':
                        self.csv_invalid_fields.append(
                            csv_row['Scientific name'])
                    else:
                        self.csv_invalid_fields.append(
                            'Unspecified scientific name')
                # else (if latitude and longitude are correct)
                else:
                    # write row to the corrected csv file
                    csv_writer.writerow(csv_row)
        # display download info
        self.emit(SIGNAL('info'))


DOWNLOADING_FORM, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__),
    'natusfera_qgis_dialog_downloading.ui'))
class NatusferaQGISDialogDownloading(QDialog, DOWNLOADING_FORM):
    def __init__(
        self, parent, csv_page, csv_totalpages, text, csv_dir,
        csv_corrected_dir, url):
        # set up dialog
        super(NatusferaQGISDialogDownloading, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        self.setupUi(self)
        self.downloading_progress_bar.setValue(csv_page)
        self.downloading_progress_bar.setMaximum(csv_totalpages)
        self.downloading_label.setText(text)
        # set up variables
        self.csv_page = csv_page
        self.csv_dir = csv_dir
        self.csv_corrected_dir = csv_corrected_dir
        # create thread and make connections
        self.downloading_thread = DownloadingThread(
            self, csv_page, csv_totalpages + 1, csv_dir, csv_corrected_dir, url)
        QObject.connect(self.downloading_thread, SIGNAL('update'), self.update)
        QObject.connect(self.downloading_thread, SIGNAL('info'), self.info)
        self.downloading_thread.finished.connect(lambda: self.close())
        self.downloading_cancel_button.clicked.connect(lambda: self.close())
        self.downloading_thread.start()
        # display dialog
        self.show()

    def update(self):
        # update progress bar
        self.csv_page += 1
        self.downloading_progress_bar.setValue(self.csv_page)

    def info(self):
        # if errors ocurred
        if len(self.downloading_thread.csv_invalid_fields) > 0:
            # set up info dialog
            download_info = QMessageBox()
            download_info.setWindowTitle('Invalid fields found')
            download_info.setText(
                '{0} invalid fields were found and deleted'.format(
                    len(self.downloading_thread.csv_invalid_fields)))
            download_info.setDetailedText(
                '\n'.join(self.downloading_thread.csv_invalid_fields))
            download_info.setStandardButtons(QMessageBox.Ok)
            download_info.setDefaultButton(QMessageBox.Ok)
            download_info.setEscapeButton(QMessageBox.Ok)
            # display info dialog
            ret = download_info.exec_()

    def closeEvent(self, event):
        # remove csv
        if os.path.isfile(self.csv_dir):
            os.remove(self.csv_dir)
        # if thread is running (this means that the dialog was cancelled)
        if self.downloading_thread.isRunning():
            # terminate thread
            self.downloading_thread.terminate()
            # remove corrected csv
            if os.path.isfile(self.csv_corrected_dir):
                os.remove(self.csv_corrected_dir)
        # close dialog
        event.accept()


class NatusferaQGIS:
    def __init__(self, iface):
        # initialize plugin
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        # inti graphical user interface and connect components
        self.dialog = NatusferaQGISDialogBase()
        self.dialog.load_csv_username_button.clicked.connect(
            lambda: self.load(input_type = 'username'))
        self.dialog.load_csv_project_button.clicked.connect(
            lambda: self.load(input_type = 'project'))
        self.dialog.load_csv_species_button.clicked.connect(
            lambda: self.load(input_type = 'species'))
        self.dialog.load_csv_everything_button.clicked.connect(
            lambda: self.load(input_type = 'everything'))
        self.dialog.username_line_edit.returnPressed.connect(
            lambda: self.load(input_type = 'username'))
        self.dialog.project_line_edit.returnPressed.connect(
            lambda: self.load(input_type = 'project'))
        self.dialog.species_line_edit.returnPressed.connect(
            lambda: self.load(input_type = 'species'))
        # create an action that will start plugin configuration
        self.action = QAction(
            QIcon(':/plugins/NatusferaQGIS/icon.png'),
            'Natusfera QGIS', self.iface.mainWindow())
        # connect the action to the run method
        self.action.triggered.connect(lambda: self.dialog.show())
        # add toolbar button and menu item
        self.iface.addPluginToMenu('Natusfera QGIS', self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        # removes the plugin menu item and icon from QGIS GUI
        self.iface.removePluginMenu('Natusfera QGIS', self.action)
        self.iface.removeToolBarIcon(self.action)

    def load(self, input_type):
        # username input
        if input_type == 'username':
            # set up url, name and filename
            url = 'http://natusfera.gbif.es/observations/'\
                '{0}.csv/?page={1}&per_page={2}'
            name = self.dialog.username_line_edit.text().lower()
            name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
            name = re.sub(' +', ' ', name)
            name = name.strip()
            filename = name

        # project input
        elif input_type == 'project':
            # set up url, name and filename
            url = 'http://natusfera.gbif.es/observations/project/'\
                '{0}.csv/?page={1}&per_page={2}'
            name = self.dialog.project_line_edit.text().lower()
            name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
            name = re.sub(r'([^\s\w])+', ' ', name)
            name = re.sub(' +', ' ', name)
            name = name.strip()
            name = name.replace(' ', '-')
            filename = name

        # species input
        elif input_type == 'species':
            # set up url, name and filename
            url = 'http://natusfera.gbif.es/observations.csv/'\
                '?taxon_name={0}&page={1}&per_page={2}'
            name = self.dialog.species_line_edit.text().lower()
            name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
            name = re.sub(' +', ' ', name)
            name = name.strip()
            filename = name.replace(' ', '-')

        # everything input
        elif input_type == 'everything':
            # set up url, name and filename
            url = 'http://natusfera.gbif.es/observations.csv/'\
                '?taxon_name={0}&page={1}&per_page={2}'
            name = ''
            filename = 'everything'

        if filename == '':
            # empty input error
            QMessageBox.critical(self.dialog, 'error', 'Please enter text.')
            return
        try:
            name.decode('utf-8')
        except UnicodeError:
            # ascii error
            QMessageBox.critical(
                self.dialog, 'error', 'Invalid ascii characters found.')
            return
        try:
            # url_test is a testing variable (will be deleted later)
            url_test = urllib2.urlopen(url.format(name, 1, 1))
        except HTTPError:
            # invalid username error
            QMessageBox.critical(self.dialog, 'error', 'Username not found.')
            return
        except URLError:
            QMessageBox.critical(
                # internet error
                self.dialog, 'error', 'No internet connection.')
            return
        try:
            url_test.info()['X-Page']
        except KeyError:
            # invalid project error
            QMessageBox.critical(self.dialog, 'error', 'Project not found.')
            return
        if url_test.read() == '':
            if input_type == 'species':
                # invalid species error
                QMessageBox.critical(self.dialog, 'error', 'Species not found.')
                return
            if input_type == 'username':
                # username with no observations error
                QMessageBox.critical(
                    self.dialog, 'error', 'This user has no observations.')
                return
            if input_type == 'project':
                # project with no observations error
                QMessageBox.critical(
                    self.dialog, 'error', 'This project has no observations.')
                return
        del url_test

        # display file dialog and save chosen directory
        csv_output = QFileDialog.getExistingDirectory(
            self.dialog, 'Working directory')
        # if dialog is canceled, return
        if not csv_output:
            return
        if os.path.isdir(csv_output) == False:
            # invalid output directory error
            QMessageBox.critical(self.dialog, 'error', 'Folder not found.')
            return
        # set up csv directories
        csv_dir = '{0}/.{1}.csv'.format(csv_output, filename)
        csv_corrected_dir = '{0}/{1}.csv'.format(csv_output, filename)

        # update url template
        url = url.format(name, '{0}', 200)
        # save http variables
        url_info = urllib2.urlopen(url.format(1))
        csv_page = int(url_info.info()['X-Page'])
        csv_perpage = int(url_info.info()['X-Per-Page'])
        csv_totalentries = int(url_info.info()['X-Total-Entries'])
        csv_totalpages = float(csv_totalentries) / float(csv_perpage)
        del url_info
        # if total pages is a decimal number
        if csv_totalpages.is_integer() == False:
            # convert it to integer and add one
            csv_totalpages = int(csv_totalpages) + 1
        # start download
        dialog_downloading = NatusferaQGISDialogDownloading(
            self.dialog, csv_page, csv_totalpages + 1,
            'Downloading {0}.csv'.format(filename), csv_dir, csv_corrected_dir,
            url)
        # while downloading keep updating the user interface
        while dialog_downloading.downloading_thread.isRunning():
            QCoreApplication.processEvents()

        # if csv file does not exist, return
        if not os.path.isfile(csv_corrected_dir):
            return

        # set up QGIS delimited text layer
        uri = QUrl.fromLocalFile(csv_corrected_dir)
        uri.addQueryItem('type', 'csv')
        uri.addQueryItem('xField', 'Longitude')
        uri.addQueryItem('yField', 'Latitude')
        uri.addQueryItem('spatialIndex', 'no')
        uri.addQueryItem('subsetIndex', 'no')
        uri.addQueryItem('watchFile', 'no')
        uri.addQueryItem('crs', 'EPSG:4326')
        layer = QgsVectorLayer(
            str(uri.toEncoded()), '{0}_layer'.format(filename), 'delimitedtext')
        # display QGIS layer
        QgsMapLayerRegistry.instance().addMapLayer(layer)

        # close dialog
        self.dialog.close()
