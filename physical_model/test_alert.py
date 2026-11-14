from alert import habitat_check, verify_note

NOMINAL = {"cabin_temp_c": 22, "cabin_humidity_pct": 45, "cabin_co2_ppm": 2000}


def test_high_co2_clears():
    snapshot = {**NOMINAL, "cabin_co2_ppm": 4000}
    result = habitat_check(lambda row: row["cabin_co2_ppm"] / 5000, snapshot, NOMINAL, 0.6)
    assert result == {"driver": "habitat", "targets": {**NOMINAL, "cabin_co2_ppm": 2900}}


def test_cardiovascular_shift_remains():
    snapshot = {**NOMINAL, "pulse_bpm": 115, "systolic_mmhg": 83}
    result = habitat_check(lambda row: (row["pulse_bpm"] - row["systolic_mmhg"]) / 50,
                           snapshot, NOMINAL, 0.6)
    assert result == {"driver": "physiological", "targets": None}


def test_rejects_invented_number():
    assert not verify_note("Verify the pulse was 140 bpm.", {"measurements": {"pulse_bpm": 80}})
