"""Shared playback core for the video players in this project family.

Three standalone applications embed a video player and are driven by an
orchestrator through files on disk: Nau and Genau (in the ``genau`` repo) and
Fun Time's satellites (in the ``fun_time`` repo).  Everything they had to agree
on lives here — the libmpv wrapper, the playlist file format, the command/paused
file channel, the status file writer, and the chrome their in-video HUDs are
drawn on — so no application has to import another application's internals to
get it.

Nothing app-specific belongs in this package.  A module earns a place here only
once a second repo needs it; until then it stays with the app that owns it.
"""
