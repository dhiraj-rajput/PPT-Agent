from utils.encryption import encrypt_data, decrypt_data
from app.core.action_scheduler import get_account_caps, get_caps_for_stage
from pipeline.linkedin.outreach.login_capture import generate_fingerprint

def test_encryption_decryption():
    """Test encrypting and decrypting data."""
    test_string = '{"li_at": "session_token_12345", "JSESSIONID": "ajax:98765"}'
    
    # 1. Encrypt
    encrypted = encrypt_data(test_string)
    assert encrypted != test_string
    assert len(encrypted) > 20
    
    # 2. Decrypt
    decrypted = decrypt_data(encrypted)
    assert decrypted == test_string

def test_encryption_empty():
    """Test encrypting and decrypting empty input."""
    assert encrypt_data("") == ""
    assert decrypt_data("") == ""

def test_action_scheduler_caps():
    """Test warmup stages caps return correct values."""
    # Stage 0
    conn_0, msg_0 = get_account_caps(0)
    assert conn_0 == 5
    assert msg_0 == 8

    # Stage 2
    conn_2, msg_2 = get_account_caps(2)
    assert conn_2 == 12
    assert msg_2 == 18

    # Steady State (Stage 4+)
    conn_steady, msg_steady = get_account_caps(4)
    assert conn_steady == 20
    assert msg_steady == 35

def test_fingerprint_generation():
    """Test regional fingerprint generation generates valid profiles."""
    # USA region
    fp_usa = generate_fingerprint("usa")
    assert "user_agent" in fp_usa
    assert fp_usa["viewport"] == "1280x800"
    assert fp_usa["timezone"] == "America/New_York"
    assert fp_usa["locale"] == "en-US"
    assert fp_usa["webgl_seed"] != ""

    # Asia region
    fp_asia = generate_fingerprint("asia")
    assert fp_asia["timezone"] == "Asia/Singapore"
    assert fp_asia["locale"] == "en-SG"

    # Fallback region
    fp_other = generate_fingerprint("nonexistent_region")
    assert fp_other["timezone"] == "UTC"
    assert fp_other["locale"] == "en-US"
