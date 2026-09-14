from app import Role, Store, User


def make_user(store: Store, username: str, role: Role = "patient") -> User:
    user = User(id=f"id-{username}", username=username, role=role, password_hash="h")
    with store.lock:
        store.users[user.id] = user
        store.username_index[user.username] = user.id
    return user


def test_register_two_distinct_usernames():
    store = Store()
    make_user(store, "alice")
    make_user(store, "bob")
    assert set(store.username_index) == {"alice", "bob"}
    assert len(store.users) == 2


def test_reset_clears_users_and_index():
    store = Store()
    make_user(store, "alice")
    store.reset()
    assert store.users == {}
    assert store.username_index == {}
