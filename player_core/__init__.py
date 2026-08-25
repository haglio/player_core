"""Shared playback core for the video players in this project family.

Six players and hosts across three repos read it: Nau and Genau (``genau``);
Fun Time's satellites, its VR player and the orchestrator itself (``fun_time``);
and Origenerator, which floats this family's console and drive readout over its
own slideshows.  Everything they had to agree on lives here — the libmpv
wrapper, the playlist file format, the command and paused-flag file channel, the
status writer, the T-Code wire, the stroke, and the chrome their in-video HUDs
are drawn on — so no application has to import another application's internals
to get it.

Nothing app-specific belongs in this package.  A module earns a place here only
once a second repo needs it; until then it stays with the app that owns it.
"""
