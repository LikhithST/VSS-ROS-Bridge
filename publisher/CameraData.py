from gi.repository import Gst
import numpy
import gi
import threading
import time
import pygame
from enum import IntEnum

import globals as G
#from com_adapter.quic_adapter import QuicDgramSource

gi.require_version('GstRtspServer', '1.0')
from gi.repository import GstRtspServer

class CameraState(IntEnum):
    INITIAL = 0
    READY = 1
    FAIL = 2

class CameraData:
    # Usage of class and instance variables:
    # https://docs.python.org/3/tutorial/classes.html

    def __init__(self, offsetRight = 1.0):
        # image aquired from camera
        self.new_imgData = None
        self.new_width = None
        self.new_height = None
        self.new_imgAvaiable = False

        # image as processed to be displayed in openGL:
        self.picture = None
        self.width = 0
        self.height = 0
        self.lastUpdate = 0
        self.offsetRight = offsetRight

    def state(self):
        if self.picture is None:
            return CameraState.INITIAL
        if (pygame.time.get_ticks() - self.lastUpdate) > G.MAX_CAMERA_LOSS_MS:
            return CameraState.FAIL
        return CameraState.READY

class GstCamera(CameraData):

    def __init__(self, rotate180 = False):
        CameraData.__init__(self)
        self.playing = False

        if rotate180:
            self.filter = "! videoflip method=rotate-180"
        else:
            self.filter = ""

    def play(self):
        ret = self.pipeline.set_state(Gst.State.PLAYING)

        if ret == Gst.StateChangeReturn.FAILURE:
            #G.Logger.error("msg", ["GstCamera", "Error starting video stream!"])
            self.playing = False
        else:
            self.playing = True

    def stop(self):
        ret = self.pipeline.set_state(Gst.State.NULL)
        if ret == Gst.StateChangeReturn.FAILURE:
            G.Logger.error("msg", ["GstCamera", "Error stopping video stream!"])
        self.playing = False

    def gst_new_buffer_callback(self, sink, data):
        """callback function whenever a new image from the camera is present"""
        sample = self.sink.emit("pull-sample")

        # get sample buffer
        buf = sample.get_buffer()

        # We can't use Gst.Buffer.extract() to read the data as it crashes
        # when called through PyGObject. We also can't use
        # Gst.Buffer.extract_dup() because we have no way in Python to free
        # the memory that it returns. Instead we get access to the actual
        # data via Gst.Memory.map().
        #
        # See:
        # https://github.com/beetbox/audioread/blob/master/audioread/gstdec.py#L316
        #
        mem = buf.get_all_memory()
        success, info = mem.map(Gst.MapFlags.READ)
        if success:
            if isinstance(info.data, memoryview):
                # We need to copy the data as the memoryview is released
                # when we call mem.unmap()
                data = bytes(info.data)
            else:
                # GStreamer Python bindings <= 1.16 return a copy of the
                # data as bytes()
                data = info.data
            mem.unmap(info)

            # get image attributes
            caps = sample.get_caps()
            self.new_height = caps.get_structure(0).get_value('height')
            self.new_width = caps.get_structure(0).get_value('width')
            #format = caps.get_structure(0).get_value('format')

            # provide image as numpy array
            self.new_imgData = numpy.ndarray((self.new_height, self.new_width, 3), buffer=data, dtype=numpy.uint8)

            # announce the image as available
            self.new_imgAvaiable = True

        return Gst.FlowReturn.OK


class GstUdpCamera(GstCamera):

    def __init__(self, port, rotate180 = False):
        GstCamera.__init__(self, rotate180)

        # define pipeline
        self.pipeline = Gst.parse_launch('udpsrc name=source ! application/x-rtp,clock-rate=90000 ! rtph264depay ! avdec_h264 %s ! videoconvert ! appsink name=sink sync=False' % (self.filter))

        # get source and sink
        self.source = self.pipeline.get_by_name("source")
        self.sink = self.pipeline.get_by_name("sink")

        if not self.source or not self.sink or not self.pipeline:
            print("Not all elements could be created.")
            exit(-1)

        self.source.set_property("port", port)
        self.source.set_property("address", G.IP_ADDRESS)

        # configure custom video sink
        self.sink.set_property("emit-signals", True)
        self.sink.connect("new-sample", self.gst_new_buffer_callback, self.sink)

        caps = Gst.caps_from_string("video/x-raw, format=(string){RGB}")
        self.sink.set_property("caps", caps)


class GstQuicCamera(GstCamera):

    def __init__(self, port, rotate180 = False):
        GstCamera.__init__(self, rotate180)

        # define pipeline
        self.pipeline = Gst.parse_launch('appsrc name=source is-live=True ! application/x-rtp,clock-rate=90000 ! rtph264depay ! avdec_h264 %s ! videoconvert ! appsink name=sink sync=False' % (self.filter))

        # get source and sink
        self.source = self.pipeline.get_by_name("source")
        self.sink = self.pipeline.get_by_name("sink")

        if not self.source or not self.sink or not self.pipeline:
            print("Not all elements could be created.")
            exit(-1)

        # create quic source
        self.quicsrc = QuicDgramSource((G.IP_ADDRESS, port), G.MPQUIC_DUPLICATE_LEVEL, self.quic_dgram_callback)

        # configure custom video sink
        self.sink.set_property("emit-signals", True)
        self.sink.connect("new-sample", self.gst_new_buffer_callback, self.sink)

        caps = Gst.caps_from_string("video/x-raw, format=(string){RGB}")
        self.sink.set_property("caps", caps)

    def quic_dgram_callback(self, buffer, len):
        #G.Logger.log("msg", ["GstQuicCamera", "QUIC Datagram received: %i" % (len)])
        if buffer and len > 0:
            gstbuf = Gst.Buffer.new_wrapped(buffer)
            self.source.emit("push-buffer", gstbuf)


class GstWebcamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, devices):
        GstRtspServer.RTSPMediaFactory.__init__(self)
        self.fps = 30
        self.bitrate = 1024 * 6
        self.pipelines = []

        # add initial fake pipeline
        self.add_pipeline(None)

        # add one pipeline for each device
        for device in devices:
            self.add_pipeline(device)

    def add_pipeline(self, device):
        if device is None:
            source = "videotestsrc pattern=ball is-live=true"
        else:
            source = "v4l2src device={}".format(device)
        source_format = "video/x-raw,framerate={}/1".format(self.fps)
        scale = "queue max-size-buffers=1 ! videoscale method=lanczos ! video/x-raw,width=1280,height=720"
        convert = "queue max-size-buffers=1 ! videoconvert"
        tuning = "speed-preset=ultrafast psy-tune=film tune=zerolatency key-int-max=15 intra-refresh=true"
        encoder = "queue max-size-buffers=1 ! x264enc bitrate={} {} ! video/x-h264,profile=main,format=I420".format(self.bitrate, tuning)
        transport = "rtph264pay config-interval=1 name=pay0 pt=96"
        self.pipelines.append("( {source} ! {source_format} ! {scale} ! {convert} ! {encoder} ! {transport} )".format(**locals()))

    def do_create_element(self, url):
        print("Webcam requested; {}, {}".format(url.abspath, url.query))
        if url.abspath.startswith('/webcam/stream='):
            try:
                index = int(url.abspath.split('=')[1])
                if len(self.pipelines) < index + 2:
                    return Gst.parse_launch(self.pipelines[0])
                else:
                    return Gst.parse_launch(self.pipelines[index + 1])
            except TypeError:
                return Gst.parse_launch(self.pipelines[0])
        else:
            return Gst.parse_launch(self.pipelines[0])       


class GstCaptureFactory(GstRtspServer.RTSPMediaFactory):
    """ Inspired by https://github.com/davidvuong/gstreamer-test/blob/master/src/python/opencv-rtsp-server.py """

    def __init__(self, height, width):
        GstRtspServer.RTSPMediaFactory.__init__(self)
        self.height = height
        self.width = width
        self.framebuffer = None
        self.fps = 30
        self.bitrate = 1024 * 6

        # create synchronization lock
        self.lock = threading.Lock()

        source = "appsrc name=source is-live=true format=GST_FORMAT_TIME do-timestamp=true"
        source_format = "video/x-raw,framerate={}/1,format=RGB,width={},height={}".format(self.fps, self.width, self.height)
        scale = "queue max-size-buffers=1 ! videoflip method=vertical-flip ! videoscale method=lanczos ! video/x-raw,width=1280,height=536"
        convert = "queue max-size-buffers=1 ! videoconvert"

        if Gst.Plugin.load_by_name("nvenc"):
            print("Hardware acceleration for video-encoding enabled.")
            encoder = "queue max-size-buffers=1 ! nvh264enc ! video/x-h264,profile=main,format=I420"
        else:
            print("Hardware acceleration for video-encoding disabled.")
            tuning = "speed-preset=ultrafast psy-tune=film tune=zerolatency key-int-max=15 intra-refresh=true"
            encoder = "queue max-size-buffers=1 ! x264enc bitrate={} {} ! video/x-h264,profile=high,format=I420".format(self.bitrate, tuning)

        transport = "rtph264pay config-interval=1 name=pay0 pt=96"
        self.pipeline = "( {source} ! {source_format} ! {scale} ! {convert} ! {encoder} ! {transport} )".format(**locals())

    def do_create_element(self, url):
        return Gst.parse_launch(self.pipeline)

    def do_configure(self, rtsp_media):
        print("do_configure: {} {}".format(rtsp_media, rtsp_media.get_status()))
        gst_source = rtsp_media.get_element().get_child_by_name("source")
        gst_source.connect('need-data', self.on_needdata)

    def on_needdata(self, src, length):
        # wait initially until a framebuffer exists
        while self.framebuffer is None:
            time.sleep(0.1)

        # create a new gst buffer
        gstbuf = Gst.Buffer.new_allocate(None, self.framebuffer.size, None)

        # lock the framebuffer for read access
        self.lock.acquire(blocking=True)
        try:
            gstbuf.fill(0, self.framebuffer.tobytes())
        finally:
            self.lock.release()

        retval = src.emit("push-buffer", gstbuf)

        if retval != Gst.FlowReturn.OK:
            print(retval)


class GstCaptureServer(object):
    def __init__(self, port, height, width, path = "/display", webcams = []):
        self.path = path
        self.port = port
        self.webcams = webcams

        # create factory
        self.factory = GstCaptureFactory(height, width)
        if self.webcams is not None:
            self.webcam_factory = GstWebcamFactory(self.webcams)

        # link framebuffer
        self.framebuffer = numpy.ndarray((height, width, 3), dtype=numpy.uint8)

    def start(self):
        # setup RTSP server
        self.server = GstRtspServer.RTSPServer()
        self.server.set_service(str(self.port))
        self.factory.set_shared(True)
        m = self.server.get_mount_points()
        m.add_factory(self.path, self.factory)
        if self.webcams is not None:
            m.add_factory('/webcam', self.webcam_factory)
        self.server.attach()

    def begin_capture(self):
        return self.factory.lock.acquire(blocking=True)

    def end_capture(self):
        self.factory.framebuffer = self.framebuffer
        self.factory.lock.release()
