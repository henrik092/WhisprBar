"""Audio capture and processing package for WhisprBar.

Re-exports all public symbols for backwards compatibility with
code that imports from whisprbar.audio directly.
"""

from .processing import (
    SAMPLE_RATE,
    CHANNELS,
    BLOCK_SIZE,
    NOISEREDUCE_AVAILABLE,
    apply_noise_reduction,
    split_audio_into_chunks,
)

from .vad import (
    VAD_AVAILABLE,
    VAD_MONITOR_QUEUE,
    vad_monitor_lock,
    vad_auto_stop_monitor,
    apply_vad,
)

from .recorder import (
    AUDIO_QUEUE,
    audio_queue_lock,
    recording_state,
    _recording_callbacks,
    recording_callback,
    start_recording,
    stop_recording,
    set_recording_callbacks,
    get_recording_state,
    list_input_devices,
    find_device_index_by_name,
    update_device_index,
)

__all__ = [
    # Constants
    "SAMPLE_RATE",
    "CHANNELS",
    "BLOCK_SIZE",
    # Availability flags
    "VAD_AVAILABLE",
    "NOISEREDUCE_AVAILABLE",
    # Queues and state
    "AUDIO_QUEUE",
    "VAD_MONITOR_QUEUE",
    "audio_queue_lock",
    "vad_monitor_lock",
    "recording_state",
    # Recording
    "recording_callback",
    "start_recording",
    "stop_recording",
    "set_recording_callbacks",
    "get_recording_state",
    "list_input_devices",
    "find_device_index_by_name",
    "update_device_index",
    # VAD
    "vad_auto_stop_monitor",
    "apply_vad",
    # Processing
    "apply_noise_reduction",
    "split_audio_into_chunks",
]
