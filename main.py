import arcade
from pyglet.event import EVENT_HANDLE_STATE


class Player(arcade.Sprite):
    def __init__(self):
        super().__init__()
        self.texture = arcade.load_texture("img.png")
        self.scale = 0.6
        self.speed = 150
        self.center_x = 400
        self.center_y = 200

    def update(self, delta_time, pressed_keys) -> None:
        dx, dy = 0, 0
        if arcade.key.W in pressed_keys:
            dy = self.speed * delta_time
        if arcade.key.S in pressed_keys:
            dy = -self.speed * delta_time
        if arcade.key.A in pressed_keys:
            dx = -self.speed * delta_time
        if arcade.key.D in pressed_keys:
            dx = self.speed * delta_time

        if dx != 0 and dy != 0:
            dx *= 0.701
            dy *= 0.701

        self.center_x += dx
        self.center_y += dy


class MyGame(arcade.Window):
    def __init__(self, width, height, title):
        super().__init__(width, height, title)
        arcade.set_background_color(arcade.color.TEA_GREEN)

    def setup(self):
        self.player = Player()
        self.player_list = arcade.SpriteList()
        self.player_list.append(self.player)

        self.pressed_keys = set()

    def on_draw(self) -> EVENT_HANDLE_STATE:
        self.clear()
        self.player_list.draw()

    def on_update(self, delta_time: float) -> bool | None:
        self.player.update(delta_time, self.pressed_keys)

    def on_key_press(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        self.pressed_keys.add(symbol)

    def on_key_release(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        self.pressed_keys.remove(symbol)


def main():
    game = MyGame(800, 600, "Мир Камиля")
    game.setup()
    arcade.run()

if __name__ == "__main__":
    main()
