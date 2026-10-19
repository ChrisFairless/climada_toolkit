# Tropical Cyclone data from the CLIMADA Data API

(TODO: documentation)

A wrapper around the CLIMADA Data API interface for tropical cyclones with a couple of convenience functions for accessing

- observed tracks
- historical and future climate synthetic tracks from the Data API

Note historic tracks are incomplete and were created before some bugs in the CLIMADA implementation of the Holland wind model were fixed. It's better to generate the wind fields directly.

Similarly the synthetic track set is very small (10x the historical record) and has known biases.