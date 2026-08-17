"""복원된 DB 의 프로필이 실제로 열리는지 확인한다.

지금까지의 복원 검사는 행 수를 세고 알려진 금융 값이 평문으로 보이지
않는지만 봤다. 그 검사는 **무작위 바이트열이어도 통과한다.** 암호화가
됐다는 것만 확인할 뿐 되돌릴 수 있다는 것은 확인하지 못한다.

프로필은 애플리케이션 레벨에서 암호화돼 있어서, 키를 잃으면 DB 를 완벽히
복원해도 남는 것은 열 수 없는 바이트열이다. 그래서 리허설의 합격 기준은
"행이 돌아왔다" 가 아니라 **"행을 복호화했다"** 여야 한다.

복호화 결과는 어디에도 남기지 않는다. 이 모듈이 내보내는 것은 건수와
key id 뿐이다 - key id 는 이미 행에 평문으로 들어 있는 값이다.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import FinancialProfileRecord
from app.security.profile_encryption import (
    ProfileDecryptionError,
    ProfileEncryptionKeyring,
)


@dataclass(frozen=True)
class RestoreVerification:
    profiles: int
    decrypted: int
    failed: int
    key_ids: tuple[str, ...]
    unavailable_key_ids: tuple[str, ...]

    @property
    def recoverable(self) -> bool:
        # 0 건은 성공이 아니다. 복원은 됐는데 프로필이 하나도 없으면 이
        # 리허설은 복구 가능성에 대해 아무것도 증명하지 못한 것이다.
        return self.profiles > 0 and self.failed == 0


def verify_restored_profiles(
    session_factory: sessionmaker[Session],
    keyring: ProfileEncryptionKeyring,
) -> RestoreVerification:
    available = keyring.key_ids
    seen: set[str] = set()
    unavailable: set[str] = set()
    profiles = 0
    decrypted = 0

    with session_factory() as session:
        # 전체를 훑는다. 표본만 열어보면 특정 세대 키로 쓰인 행만 못 여는
        # 경우를 놓친다. 키 로테이션 중이면 정확히 그 상황이 생긴다.
        records = session.scalars(select(FinancialProfileRecord)).all()

    for record in records:
        profiles += 1
        seen.add(record.encryption_key_id)
        if record.encryption_key_id not in available:
            unavailable.add(record.encryption_key_id)
            continue
        try:
            # 반환값은 버린다. 평문 프로필을 변수에 담아둘 이유가 없다.
            keyring.decrypt(
                record.encrypted_profile,
                record.encryption_key_id,
                UUID(record.profile_id),
            )
        except (ProfileDecryptionError, ValueError):
            continue
        decrypted += 1

    return RestoreVerification(
        profiles=profiles,
        decrypted=decrypted,
        failed=profiles - decrypted,
        key_ids=tuple(sorted(seen)),
        unavailable_key_ids=tuple(sorted(unavailable)),
    )
