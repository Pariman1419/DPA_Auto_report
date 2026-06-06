from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class BackgroundInfo(BaseModel):
    customerName: str = ""
    assemblySite: str = ""
    packageType: str = ""
    dateCode: str = ""
    packageSize: str = ""
    numberOfLot: str = ""
    pinBallCount: str = ""
    requestorNameDept: str = ""
    reliabilityStaffName: str = ""
    relRequestNumber: str = ""


class BillOfMaterial(BaseModel):
    orderLot: str = ""
    custAssy: str = ""
    device: str = ""
    dieSize: str = ""
    dapSize: str = ""
    lfStockNo: str = ""
    dieAttachMaterial: str = ""
    wireType: str = ""
    moldCompound: str = ""
    platingFinish: str = ""


class TestStep(BaseModel):
    name: str
    duration: Optional[str] = None
    condition: Optional[str] = None
    sampleSize: Optional[str] = None
    result: Optional[str] = None
    planStart: Optional[str] = None
    planFinish: Optional[str] = None
    status: Optional[str] = None


class ReliabilityTest(BaseModel):
    name: str
    duration: Optional[str] = None
    condition: Optional[str] = None
    sampleSize: Optional[str] = None
    status: Optional[str] = None
    planStart: Optional[str] = None
    planFinish: Optional[str] = None
    steps: List[TestStep] = []


class ProductRequestData(BaseModel):
    productRequestNo: str
    folderName: Optional[str] = None
    subject: str = ""
    purpose: str = ""
    date: str = ""
    conclusion: str = ""
    summary: dict = Field(default_factory=dict)
    backgroundInfo: BackgroundInfo = Field(default_factory=BackgroundInfo)
    billOfMaterial: Optional[BillOfMaterial] = None
    reliabilityTests: List[ReliabilityTest] = []
    dpaItems: List[str] = []


class ProductRequestListItem(BaseModel):
    folderName: Optional[str] = None
    productRequestNo: str
    hasExcel: bool = True


class GenerateReportRequest(BaseModel):
    prNumber: str
    timepoint: str
    lot: str
    selectedSections: dict[str, bool]
    userId: str = "System"
    revision: str = "A"


class LoginRequest(BaseModel):
    userId: str
    password: str


class LoginResponse(BaseModel):
    status: str
    user: Optional[dict] = None
    message: Optional[str] = None


class RegisterRequest(BaseModel):
    userId: str
    fullName: str
    password: str
    email: Optional[EmailStr] = None
    role: Optional[str] = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict
