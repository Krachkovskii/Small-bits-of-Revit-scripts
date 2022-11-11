import sys
import clr
import random
clr.AddReference('ProtoGeometry')
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from math import pi, degrees, sin
from Autodesk.Revit.Creation import ItemFactoryBase
import Autodesk.DesignScript.Geometry as DS
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import *
from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommonButtons,TaskDialogCommandLinkId, TaskDialogResult)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

### this script gen

class FloorSelectionFilter(ISelectionFilter):
	"""Selection filter that allows only elements with "Floors" category name"""
	def __init__(self):
		pass
	def AllowElement(self, element):
		if element.Category.Name == "Floors":
			return True
		else:
			return False
	def AllowReference(self, element):
		return False


def BboxScale(bbox, valueX, valueY, valueZ):
	"""
	Equally extends the BoundingBox by given distance in feet.
	0 will leave the BB dimension intact.
	"""
	bbox.Min = XYZ((bbox.Min.X - (valueX/2)), (bbox.Min.Y - (valueY/2)), (bbox.Min.Z - (valueZ/2)))
	bbox.Max = XYZ((bbox.Max.X + (valueX/2)), (bbox.Max.Y + (valueY/2)), (bbox.Max.Z + (valueZ/2)))
	return bbox


def BboxMove(bbox, valueX, valueY, valueZ):
	"""Moves the BoundingBox by given distance in feet."""
	bbox.Min = XYZ((bbox.Min.X + valueX), (bbox.Min.Y + valueY), (bbox.Min.Z + valueZ))
	bbox.Max = XYZ((bbox.Max.X + valueX), (bbox.Max.Y + valueY), (bbox.Max.Z + valueZ))
	return bbox


def BBoxCenter(bbox):
	"""Calculates the centerpoint of given BoundingBox"""
	dX = (bbox.Min.X + bbox.Max.X) / 2
	dY = (bbox.Min.Y + bbox.Max.Y) / 2
	dZ = (bbox.Min.Z + bbox.Max.Z) / 2
	return XYZ(dX, dY, dZ)


def SortPanels(floor, panels):
	"""
	Sort Curtain Panels: creates set of lines from floor centerpoint to each panel centerpoint,
	sorts the panels based on 0-360° value
	"""
	# vectors need to be aligned to the plane, so their Z-point is aligned to the floor level height
	floorLevel = doc.GetElement(floor.LevelId).ProjectElevation

	floorCenter = BBoxCenter(floor.get_BoundingBox(None))
	floorCenter = XYZ(floorCenter.X, floorCenter.Y, floorLevel)
	panelCenters = [BBoxCenter(cp.get_BoundingBox(None)) for cp in panels] 
	panelCenters = [XYZ(pc.X, pc.Y, floorLevel) for pc in panelCenters]
	
	vectors = [Line.CreateBound(floorCenter, pc).Direction for pc in panelCenters]
	angles = [(degrees(v.AngleOnPlaneTo(XYZ(1,0,0), XYZ(0,0,1)))) for v in vectors]
	values = list(zip(panels, angles))
	sortedList = sorted(values, key = lambda angle: angle[1])
	return [l[0] for l in sortedList]


def ReRange(min, max, inList):
	"""Re-mapping ranges to new Min and Max value. Output: new list"""
	num = (len(inList) - 1)
	delta = (max - min) / num
	outList = [min]
	for x in range(num):
		outList.append(outList[-1] + delta)
	return outList


def CreateCurve(rep, panelHeight, panelNumber):
	"""Creates Y values based on Sine curve with given parameters: amplitude, number of repetitions and number of panels"""
	a = (panelHeight / 2) * curveHeight
	c = random.randint(0, rep) if randomShift == True else 0
	d = panelHeight / 2
	num = ReRange(0, 2*pi, range(panelNumber))
	return [(a * sin(rep * (x + c)) + d) for x in num]


doc = DocumentManager.Instance.CurrentDBDocument
uiapp = DocumentManager.Instance.CurrentUIApplication 
app = uiapp.Application 
uidoc = uiapp.ActiveUIDocument

#______INPUTS_______
refresh = IN[0] #bool just in case
dOption = UnwrapElement(IN[1]) #OOTB design option node
parameterName = IN[2] #string; parameter that controls vertical point of the curtain panel
curveHeight = IN[3] #float
curveNumber = IN[4] #int
randomShift = IN[5] #bool

TaskDialog.Show("Floor selection", "Please select Floor element from this model", TaskDialogCommonButtons.Ok)

# selecting the floor from AP model
if refresh == True or refresh == False:
	selFilter = FloorSelectionFilter()
	floorRef = uidoc.Selection.PickObject(ObjectType.Element, selFilter, "Select any Floor element from this model")
	floor = doc.GetElement(floorRef)
	
# getting boundingbox of the floor, expanding it a bit and moving up, to make sure the curtain panels intersect with it
bbox = floor.get_BoundingBox(None)
bbox = BboxScale(bbox, 3, 3, 0)
bbox = BboxMove(bbox, 0, 0, 3)

# curtain panels in selected design option that intersect this boundingbox
bbOutline = Outline(bbox.Min, bbox.Max)
bbFilter = BoundingBoxIntersectsFilter(bbOutline)
dOptFilter = ElementDesignOptionFilter(dOption.Id)
filter = LogicalAndFilter(bbFilter, dOptFilter)
floorPanels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_CurtainWallPanels).WherePasses(filter).ToElements()

panelHeight = floorPanels[0].get_Parameter(BuiltInParameter.CURTAIN_WALL_PANELS_HEIGHT).AsDouble()
sortedPanels = SortPanels(floor, floorPanels)
yValues = CreateCurve(curveNumber, panelHeight, len(floorPanels))

report = []
TransactionManager.Instance.EnsureInTransaction(doc)
for p, y in zip(sortedPanels, yValues):
	try:
		param = p.LookupParameter(parameterName)
		param.Set(y)
		report.append("Changed value")
	except:
		report.append("Something went wrong")
TransactionManager.Instance.TransactionTaskDone()

#_______OUTPUT________
OUT = report