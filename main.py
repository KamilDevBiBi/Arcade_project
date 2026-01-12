from typing import Callable

import arcade
from pyglet.event import EVENT_HANDLE_STATE
from random import randint, choice

from pyglet.graphics import Batch


class Enemy(arcade.Sprite):
    def __init__(self, y_spawn):
        super().__init__()
        self.texture = arcade.load_texture(f"assets/monsters/monster_{randint(1, 3)}.png")
        self.change_x = randint(100, 150)

        self.center_x = -self.width / 2
        self.center_y = choice(y_spawn).center_y

    def update(self, delta_time: float = 1 / 60, *args, **kwargs) -> None:
        self.center_x += self.change_x * delta_time


class Bullet(arcade.Sprite):
    def __init__(self, center_x: float, center_y: float, direction: int):
        super().__init__()
        self.texture = arcade.load_texture("assets/magic_bullet.png")
        if direction == -1:
            self.texture = self.texture.flip_horizontally()

        self.scale = 0.4

        self.change_x = 180
        self.direction = direction # Пуля летит по направлению взгляда

        self.center_x = center_x
        self.center_y = center_y

    def update(self, delta_time: float = 1 / 60, *args, **kwargs) -> None:
        self.center_x += self.change_x * self.direction * delta_time
        if self.center_x + self.width / 2 <= 0 or self.center_x - self.width / 2 >= 1500:
            self.remove_from_sprite_lists()


class Player(arcade.Sprite):
    def __init__(self):
        super().__init__()
        # Начальная текстура - герой смотрит влево
        self.left_texture = arcade.load_texture("assets/player/left_player.png")
        self.right_texture = arcade.load_texture("assets/player/right_player.png")
        self.left_attack = arcade.load_texture("assets/player/left_attack.png")
        self.right_attack = arcade.load_texture("assets/player/right_attack.png")
        self.direction = True

        self.texture = self.right_texture
        # Начальная позиция
        self.center_x = 400
        self.center_y = 200

        self.speed = 150

        self.is_dash = False
        self.dash_speed = 30
        self.boost = 4.5

        self.is_jump = False
        self.jump_speed = 30
        self.gravity = 4.5

        self.is_attacking = False # Свойство для проверки атакует ли герой
        self.attack_duration = 0.3 # Длительность анимации атаки

        self.is_reload = False
        self.is_shooted = False
        self.shot_count = 0
        self.time_since_shot = 0
        self.reload_duration = 3

        # Если персонаж бездействует, активируем анимацию
        self.staying_duration = 0.7 # Смена кадра каждые 700 мс

        # Текстуры (кадры) для анимации
        self.right_staying_textures = [self.right_texture, arcade.load_texture("assets/player/right_staying.png")]
        self.left_staying_textures = [self.left_texture, arcade.load_texture("assets/player/left_staying.png")]
        self.cur_frame = 0 # Текущий кадр - персонаж смотрит влево

    def update(self, delta_time, pressed_keys) -> None:
        # Передвижение героя
        self.update_movement(delta_time, pressed_keys)

        if self.is_attacking:
            # Если персонаж атаковал, увеличиваем время ожидания анимации до 2 секунд
            self.staying_duration = 2
            # Анимация атаки
            self.attack_duration -= delta_time
            if self.attack_duration <= 0:
                self.is_attacking = False
                self.attack_duration = 0.3
                self.texture = self.right_texture if self.direction == 1 else self.left_texture

        self.update_shooting_timer(delta_time)
        self.do_reload(delta_time)

        if self.is_dash:
            self.center_x += self.dash_speed
            self.dash_speed -= self.boost
            if self.dash_speed * self.direction <= 0:
                self.is_dash = False

    def update_movement(self, delta_time: float, pressed_keys: set):
        """Передвижение героя"""
        dx = 0
        if arcade.key.A in pressed_keys:
            # Если было право - меняем на лево (один раз)
            if self.direction == 1:
                self.direction = -1
                self.texture = self.left_texture

            dx = -self.speed * delta_time
        if arcade.key.D in pressed_keys:
            # Если было лево - меняем на право (один раз)
            if self.direction == -1:
                self.direction = 1
                self.texture = self.right_texture

            dx = self.speed * delta_time

        if dx == 0:
            # Если персонаж не двигается - начинаем анимацию
            self.staying_duration -= delta_time
            if self.staying_duration <= 0:
                self.staying_duration = 0.7
                self.cur_frame = (self.cur_frame + 1) % 2
                # В зависимости от направления устанавливаем текстуру
                if self.direction == 1:
                    self.texture = self.right_staying_textures[self.cur_frame]
                else:
                    self.texture = self.left_staying_textures[self.cur_frame]
        else:
            # Если после анимации текстура осталась на втором кадре, то меняем на первый
            if self.cur_frame == 1:
                self.cur_frame = 0
                self.texture = self.right_texture if self.direction == 1 else self.left_texture

            # Если персонаж двигался, то увеличиваем время ожидания анимации до 2 секунд
            self.staying_duration = 2

        self.center_x += dx

    def attack(self, create_bullet_callback: Callable):
        if self.is_reload:
            return

        self.is_attacking = True
        self.is_shooted = True
        self.shot_count += 1
        self.texture = self.right_attack if self.direction == 1 else self.left_attack # Меняем текстуру на атакующую

        create_bullet_callback(self.center_x + 60 * self.direction, self.center_y, self.direction)

    def make_dash(self):
        self.is_dash = True
        self.dash_speed = 30 * self.direction
        self.boost = 4.5 * self.direction

    def do_reload(self, dt: float):
        if self.is_reload:
            self.reload_duration -= dt
            if self.reload_duration <= 0:
                self.reload_duration = 3
                self.is_reload = False

    def update_shooting_timer(self, dt):
        if self.is_shooted:
            self.time_since_shot += dt
            print(self.time_since_shot)
            if self.time_since_shot >= 0.5:
                if self.shot_count >= 3:
                    self.is_reload = True

                self.is_shooted = False
                self.time_since_shot = 0
                self.shot_count = 0


class MyGame(arcade.Window):
    def __init__(self, width, height, title):
        super().__init__(width, height, title, fullscreen=True)
        self.tile_map = arcade.load_tilemap("test.tmx")
        self.scene = arcade.Scene.from_tilemap(self.tile_map)
        arcade.set_background_color(arcade.color.DARK_IMPERIAL_BLUE)

        self.world_width = 80 * 64 # Ширина карты, кол-во тайлов * ширину тайла
        self.world_height = 20 * 64 # Высота карты

        self.coins_list = self.scene["coins"]
        self.coin_catching_sound = arcade.load_sound("assets/sounds/Звук начисления очков или бонусных баллов.mp3")
        self.platforms = arcade.SpriteList()
        plat = arcade.Sprite("assets/platform.png")
        plat.left = 1536
        plat.bottom = 192
        plat.boundary_top = 600
        plat.boundary_bottom = 192
        plat.change_y = 2
        self.platforms.append(plat)

        self.world_camera = arcade.camera.Camera2D()
        self.last_y = 0
        self.gui_camera = arcade.camera.Camera2D()

    def setup(self):
        self.player = Player()
        self.player_list = arcade.SpriteList()
        self.player_list.append(self.player)

        self.player_is_jump = False
        self.jump_buffer_time = 0
        self.time_since_grounded = 1000.0
        self.jump_count = 1
        self.last_y = -1

        self.bullets_list = arcade.SpriteList()

        self.enemies_list = arcade.SpriteList()

        self.pressed_keys = set() # Для хранения нажатых кнопок
        # arcade.schedule(self.spawn_enemies, 1.5)

        self.engine = arcade.PhysicsEnginePlatformer(player_sprite=self.player, gravity_constant=1, walls=self.scene["collisions"], platforms=self.platforms)
        self.batch = Batch()
        self.coins_count = 0
        self.text_score = arcade.Text("Монеты: 0", 100, self.height - 20, arcade.color.WHITE, 24, anchor_x="left", anchor_y="top", batch=self.batch)

    def on_draw(self) -> EVENT_HANDLE_STATE:
        self.clear()

        self.world_camera.use()

        self.scene.draw()
        self.player_list.draw()
        self.bullets_list.draw()
        self.enemies_list.draw()
        self.platforms.draw()

        self.gui_camera.use()

        self.batch.draw()

    def on_update(self, delta_time: float) -> bool | None:
        self.player.update(delta_time, self.pressed_keys)
        for bullet in self.bullets_list:
            # Передвигаем пулю
            bullet.update()
            # Проверяем на попадание в монстра
            killed_enemies = arcade.check_for_collision_with_list(bullet, self.enemies_list)
            for enemy in killed_enemies:
                self.coins_count += 1
                self.text_score.text = f"Монеты: {self.coins_count}"
                enemy.remove_from_sprite_lists()
                bullet.remove_from_sprite_lists()

        catched_coins = arcade.check_for_collision_with_list(self.player, self.coins_list)
        for coin in catched_coins:
            self.coin_catching_sound.play()
            self.coins_count += 1
            self.text_score.text = f"Монеты: {self.coins_count}"
            coin.remove_from_sprite_lists()

        for enemy in self.enemies_list:
            enemy.update()

        grounded = self.engine.can_jump(y_distance=6)
        camera_position = (self.player.center_x, self.player.center_y)
        if grounded:
            self.jump_count = 1
            self.time_since_grounded = 0
        else:
            camera_position = (self.player.center_x, self.last_y)
            self.time_since_grounded += delta_time

        if self.jump_buffer_time > 0:
            self.jump_buffer_time -= delta_time

        want_jump = self.player_is_jump or (self.jump_buffer_time > 0)

        if want_jump:
            can_coyote = (self.time_since_grounded <= 0.3)
            if grounded or can_coyote:
                camera_position = (self.player.center_x, self.last_y)
                self.engine.jump(15)

                self.jump_buffer_time = 0

        self.engine.update()

        # Ширина и высота экрана, не карты!
        half_view_w = self.world_camera.viewport_width / 2
        half_view_h = self.world_camera.viewport_height / 2

        # Ограничиваем позицию камеры, чтобы не показать пустоту за краями карты
        cam_x = min(self.world_width - half_view_w, max(half_view_w, camera_position[0]))
        cam_y = min(self.world_height - half_view_h, max(half_view_h, camera_position[1]))

        camera_position = (cam_x, cam_y)

        self.world_camera.position = arcade.math.lerp_2d(
            self.world_camera.position,
            camera_position,
            0.18
        )
        self.last_y = camera_position[1]

    def on_key_press(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if symbol == arcade.key.F:
            self.player.make_dash()
        elif symbol == arcade.key.W:
            self.player_is_jump = True
        elif symbol == arcade.key.ESCAPE:
            self.close()
        self.pressed_keys.add(symbol)

    def on_key_release(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if symbol == arcade.key.W:
            self.player_is_jump = False
            if self.player.change_y > 0:
                self.player.change_y *= 0.45
        self.pressed_keys.remove(symbol)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if button == arcade.MOUSE_BUTTON_LEFT:
            # Если пользователь кликнул ЛКМ - герой атакует
            self.player.attack(self.create_bullet)

    def create_bullet(self, center_x: float, center_y: float, direction: int):
        bullet = Bullet(center_x, center_y, direction)
        self.bullets_list.append(bullet)

    # def spawn_enemies(self, delta_time):
    #     enemy = Enemy(self.monster_spawn)
    #     self.enemies_list.append(enemy)



def main():
    game = MyGame(800, 600, "Мир Камиля")
    game.setup()
    arcade.run()

if __name__ == "__main__":
    main()
