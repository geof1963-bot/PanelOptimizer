# -*- coding: utf-8 -*-

import Part

from Core.Feature import Feature
from Core.Feature import FeatureType


class FeatureExtractor:

    """
    Extraction des entités géométriques du modèle FreeCAD.

    Cette première version ne prend aucune décision.
    Elle transforme simplement un TopoShape en liste
    de Features exploitables par les modules suivants.
    """

    def __init__(self):

        self.features = []

        self.nextId = 0

    # ---------------------------------------------------------

    def extract(self, shape):

        self.features.clear()
        self.nextId = 0

        self._extractFaces(shape)

        self._extractEdges(shape)

        self._extractVertices(shape)

        self._extractBoundingBox(shape)

        return self.features

    # ---------------------------------------------------------

    def _newFeature(self, featureType):

        feature = Feature()

        feature.id = self.nextId

        self.nextId += 1

        feature.type = featureType

        self.features.append(feature)

        return feature

    # ---------------------------------------------------------

    def _extractFaces(self, shape):

        for face in shape.Faces:

            feature = self._newFeature(FeatureType.UNKNOWN)

            feature.shape = face

            feature.area = face.Area

            feature.perimeter = sum(edge.Length for edge in face.Edges)

            feature.center = face.CenterOfMass

            feature.bbox = face.BoundBox

            feature.metadata["entity"] = "FACE"

    # ---------------------------------------------------------

    def _extractEdges(self, shape):

        for edge in shape.Edges:

            feature = self._newFeature(FeatureType.EDGE)

            feature.shape = edge

            feature.center = edge.CenterOfMass

            feature.perimeter = edge.Length

            feature.metadata["entity"] = "EDGE"

    # ---------------------------------------------------------

    def _extractVertices(self, shape):

        for vertex in shape.Vertexes:

            feature = self._newFeature(FeatureType.VERTEX)

            feature.shape = vertex

            feature.center = vertex.Point

            feature.metadata["entity"] = "VERTEX"

    # ---------------------------------------------------------

    def _extractBoundingBox(self, shape):

        bb = shape.BoundBox

        feature = self._newFeature(FeatureType.BORDER)

        feature.bbox = bb

        feature.metadata["xmin"] = bb.XMin
        feature.metadata["xmax"] = bb.XMax
        feature.metadata["ymin"] = bb.YMin
        feature.metadata["ymax"] = bb.YMax
        feature.metadata["zmin"] = bb.ZMin
        feature.metadata["zmax"] = bb.ZMax

    # ---------------------------------------------------------

    def getFeatures(self):

        return self.features

    # ---------------------------------------------------------

    def getFeaturesByType(self, featureType):

        return [

            f

            for f in self.features

            if f.type == featureType

        ]