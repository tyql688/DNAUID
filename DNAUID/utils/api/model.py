from typing import List, Optional

from pydantic import BaseModel, Field


class UserGame(BaseModel):
    gameId: int = Field(description="gameId", default=268)
    gameName: str = Field(description="gameName", default="二重螺旋")


class DNALoginResponse(BaseModel):
    applyCancel: Optional[int] = Field(description="applyCancel", default=0)
    gender: Optional[int] = Field(description="gender", default=0)
    signature: Optional[str] = Field(description="signature", default="")
    headUrl: Optional[str] = Field(description="headUrl", default="")
    userName: Optional[str] = Field(description="userName", default="")
    userId: str = Field(description="userId")
    isOfficial: int = Field(description="isOfficial", default=0)
    token: str = Field(exclude=True, description="token")
    userGameList: List[UserGame] = Field(description="userGameList")
    isRegister: int = Field(description="isRegister", default=0)
    status: Optional[int] = Field(description="status", default=0)
    isComplete: Optional[int] = Field(
        description="isComplete 是否完成绑定 0: 未绑定, 1: 已绑定", default=0
    )
    refreshToken: str = Field(exclude=True, description="refreshToken")


class DNARoleShowVo(BaseModel):
    roleId: str = Field(description="roleId")
    headUrl: Optional[str] = Field(description="headUrl")
    level: Optional[int] = Field(description="level")
    roleName: Optional[str] = Field(description="roleName")
    isDefault: Optional[int] = Field(description="isDefault")
    roleRegisterTime: Optional[str] = Field(description="roleRegisterTime")
    boundType: Optional[int] = Field(description="boundType")
    roleBoundId: str = Field(description="roleBoundId")


class DNARole(BaseModel):
    gameName: str = Field(description="gameName")
    showVoList: List[DNARoleShowVo] = Field(description="showVoList")
    gameId: int = Field(description="gameId")


class DNARoleListResponse(BaseModel):
    roles: List[DNARole] = Field(description="roles")
