from typing import Callable

import arcade
from pyglet.event import EVENT_HANDLE_STATE
from random import randint, uniform

from arcade.gui import UIManager, UITextureButton, UIMessageBox, UIImage
from arcade.gui.widgets.layout import UIAnchorLayout, UIBoxLayout

from pyglet.graphics import Batch

import sqlite3
import os

GRAVITY = 1
COYOTE_TIME = 0.08
JUMP_SPEED = 24
JUMP_BUFFER = 0.12

class DamageNumber(arcade.Sprite):
    def __init__(self, center_x, center_y, cur_damage: int):
        super().__init__()
        self.texture = arcade.load_texture(f"assets/damage_number_{cur_damage}.png")

        self.center_x = center_x
        self.center_y = center_y

        self.life_time = 1 # урон над врагом будет показан только на секунду

    def update(self, delta_time: float = 1 / 60, *args, **kwargs) -> None:
        self.life_time -= delta_time
        if self.life_time <= 0:
            self.remove_from_sprite_lists()
        self.center_y += 30 * delta_time
        self.alpha -= 2.6 # примерно через секунду прозрачность станет 0


class Enemy(arcade.Sprite):
    def __init__(self):
        super().__init__()
        monster_type = randint(1, 3)
        base_texture = arcade.load_texture(f"assets/monsters/monster_{monster_type}.png")
        self.texture = base_texture.flip_horizontally()
        self.defeated_texture = arcade.load_texture(f"assets/monsters/defeated_monster_{monster_type}.png")


        self.center_x = 550
        self.center_y = 162
        self.change_x = randint(70, 110)
        self.direction = -1 # -1 или 1 (влево или вправо)

        self.change_direction = False
        self.stop_timer = uniform(0.5, 0.8)

        self.enemy_damage_sound = arcade.load_sound("assets/sounds/Звук старой игры.mp3")
        self.enemy_death_sound = arcade.load_sound("assets/sounds/delicious-sonorous-short-crunch.mp3")

        self.health = randint(9, 17) # от 2 до 5 ударов

        self.is_hitted = False
        self.is_defeated = False
        self.hit_timer = 0.1

        self.can_attack = True
        self.reload_timer = 2

    def update(self, delta_time: float, player_x: int) -> None:
        # В зависимости от положения игрока меняем направление врага
        if (player_x - self.center_x) // abs(player_x - self.center_x) != self.direction:
            self.direction *= -1
            self.texture = self.texture.flip_horizontally()
            self.change_direction = True

        if self.change_direction:
            self.stop_timer -= delta_time
            if self.stop_timer <= 0:
                self.change_direction = False
                self.stop_timer = uniform(0.5, 0.8)
        else:
            self.center_x += self.change_x * self.direction * delta_time

        if self.is_hitted:
            self.hit_timer -= delta_time
            if self.hit_timer < 0:
                self.hit_timer = 0.1
                if self.is_defeated:
                    self.remove_from_sprite_lists()
                else:
                    self.color = (255, 255, 255)

        if not self.can_attack:
            self.reload_timer -= delta_time
            if self.reload_timer <= 0:
                self.can_attack = True
                self.reload_timer = 2

    def process_bullet_hit(self, cur_damage: int):
        self.is_hitted = True

        self.health -= cur_damage
        self.is_defeated = self.health <= 0
        if self.is_defeated:
            self.enemy_damage_sound.play()
            self.texture = self.defeated_texture
        else:
            self.enemy_death_sound.play()
            self.color = (255, 128, 128)

    def reload(self):
        self.can_attack = False


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
        if self.center_x + self.width / 2 <= 0 or self.center_x - self.width / 2 >= 30 * 64:
            self.remove_from_sprite_lists()


class Player(arcade.Sprite):
    def __init__(self, user_id):
        super().__init__()
        # Начальная текстура - герой смотрит влево
        self.left_texture = arcade.load_texture("assets/player/left_player.png")
        self.right_texture = arcade.load_texture("assets/player/right_player.png")
        self.left_attack = arcade.load_texture("assets/player/left_attack.png")
        self.right_attack = arcade.load_texture("assets/player/right_attack.png")
        self.left_jump = arcade.load_texture("assets/player/left_jump.png")
        self.right_jump = arcade.load_texture("assets/player/right_jump.png")
        self.direction = 1

        self.texture = self.right_texture
        self.attack_sound = arcade.load_sound("assets/sounds/Звук всплеска магии (mp3cut.net).mp3")
        self.dash_sound = arcade.load_sound("assets/sounds/waving-a-blanket-over-camping-gear (mp3cut.net).mp3")

        # Начальная позиция
        self.center_x = 400
        self.center_y = 200

        self.feet_hitbox = arcade.LBWH(self.left + 20, self.bottom - 5, 41, 6)
        self.body_hitbox = arcade.LBWH(self.left + 21, self.bottom + 1, 34, 80)

        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        player_data = cursor.execute("SELECT * FROM players WHERE id = ?", (user_id, )).fetchone()
        health_num, damage_num, reload_num = player_data[1:4]

        # значения на нулевом и 1, 2, 3 уровни
        health_levels = [10, 13, 17, 22]
        damage_levels = [(4, 5), (5, 5), (5, 6), (6, 7)]
        reload_levels = [3, 2.5, 2, 1]

        self.health = health_levels[health_num]
        self.is_hitted = False
        self.hit_timer = 0.1
        self.damage = damage_levels[damage_num]

        self.speed = 150
        self.durability = 10
        self.is_jump = False
        self.is_climbing = False

        self.is_dash = False
        self.dash_speed = 30
        self.boost = 4.5

        self.is_attacking = False # Свойство для проверки атакует ли герой
        self.attack_duration = 0.3 # Длительность анимации атаки

        self.is_reload = False
        self.is_fired = False
        self.shot_count = 0
        self.time_since_shot = 0
        self.reload_duration = reload_levels[reload_num]

        # Если персонаж бездействует 3 секунды, активируем анимацию
        self.staying_duration = 3

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
                self.change_jump_texture()

        self.update_shooting_timer(delta_time)
        self.do_reload(delta_time)

        if self.is_dash:
            self.center_x += self.dash_speed
            self.dash_speed -= self.boost
            if self.dash_speed * self.direction <= 0:
                self.is_dash = False

        if self.is_hitted:
            self.hit_timer -= delta_time
            if self.hit_timer < 0:
                self.hit_timer = 0.1
                self.color = (255, 255, 255)
                self.is_hitted = False

        self.update_durability()

    def update_movement(self, delta_time: float, pressed_keys: set):
        """Передвижение героя"""
        dx, dy = 0, 0
        if arcade.key.A in pressed_keys:
            # Если было право - меняем на лево (один раз)
            if self.direction == 1:
                self.direction = -1
                # Текстуру меняем только когда игрок не на лестнице
                if not self.is_climbing:
                    self.texture = self.left_texture
                    self.sync_hit_box_to_texture()

            dx = -self.speed * delta_time
        if arcade.key.D in pressed_keys:
            # Если было лево - меняем на право (один раз)
            if self.direction == -1:
                self.direction = 1
                # Текстуру меняем только когда игрок не на лестнице
                if not self.is_climbing:
                    self.texture = self.right_texture
                    self.sync_hit_box_to_texture()

            dx = self.speed * delta_time
        if arcade.key.W in pressed_keys or arcade.key.S in pressed_keys:
            dy = self.change_y

        if dx == 0 and dy == 0:
            # Если персонаж не двигается - начинаем анимацию
            self.staying_duration -= delta_time
            if self.staying_duration <= 0:
                self.staying_duration = 0.7 # Смена кадра каждые 700 мс
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

            # Если персонаж двигался, то увеличиваем время ожидания анимации до 3 секунд
            self.staying_duration = 3

        self.center_x += dx

        self.feet_hitbox = arcade.LBWH(self.left + 20, self.bottom - 2, 41, 4)
        self.body_hitbox = arcade.LBWH(self.left + 21, self.bottom + 4, 34, 80)
        self.feet = [self.left + 20, self.bottom - 2, 41, 4]
        self.body = [self.left + 21, self.bottom + 4, 34, 80]

    def attack(self, create_bullet_callback: Callable):
        if self.is_reload:
            return

        self.player_sound = self.attack_sound.play()

        self.is_attacking = True
        self.is_fired = True
        self.shot_count += 1
        self.texture = self.right_attack if self.direction == 1 else self.left_attack # Меняем текстуру на атакующую

        create_bullet_callback(self.center_x + 60 * self.direction, self.center_y, self.direction)

    def process_hit(self):
        self.is_hitted = True
        self.color = (255, 128, 128)

    def make_dash(self):
        if self.durability < 5.5:
            return

        self.dash_sound.play()
        self.is_dash = True
        self.dash_speed = 30 * self.direction
        self.boost = 4.5 * self.direction

        self.durability -= 5.5
        # При рывке также увеличиваем время ожидания анимации до 3 секунд
        self.staying_duration = 3
        # Если мы прервали текущую анимацию - возвращаем первый кадр
        if self.cur_frame == 1:
            self.cur_frame = 0
            self.texture = self.right_texture if self.direction == 1 else self.left_texture

    def do_reload(self, dt: float):
        if self.is_reload:
            self.reload_duration -= dt
            if self.reload_duration <= 0:
                self.reload_duration = 3
                self.is_reload = False

    def update_shooting_timer(self, dt):
        if self.is_fired:
            self.time_since_shot += dt
            if self.time_since_shot >= 0.5:
                if self.shot_count >= 3:
                    self.is_reload = True

                self.is_fired = False
                self.time_since_shot = 0
                self.shot_count = 0

    def update_durability(self):
        # увеличиваем выносливость каждый кадр
        if self.durability < 9.9:
            self.durability += 0.1

    def change_jump_texture(self):
        if self.is_attacking:
            self.texture = self.right_attack if self.direction == 1 else self.left_attack  # Меняем текстуру на атакующую
        elif self.is_jump:
            self.texture = self.left_jump if self.direction == -1 else self.right_jump
        elif self.is_climbing:
            self.texture = arcade.load_texture("assets/player/climbing.png")
        else:
            self.texture = self.left_texture if self.direction == -1 else self.right_texture


class BetterPhysicEngine:
    def __init__(self, player: Player, walls: arcade.SpriteList, platforms: arcade.SpriteList,
                 ladders_top: arcade.SpriteList, ladders: arcade.SpriteList, finish: arcade.SpriteList):
        self.player = player
        self.target_sprites = walls
        self.platforms = platforms
        self.ladders_top = ladders_top
        self.ladders = ladders
        self.finish = finish

    def can_jump(self):
        walls = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.target_sprites)
        platforms = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.platforms)
        return len(walls) > 0 or len(platforms) > 0

    def is_on_ladder_top(self):
        top = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.ladders_top)
        return top

    def is_on_ladder(self):
        ladders = arcade.get_sprites_in_rect(self.player.body_hitbox, self.ladders)
        return len(ladders) > 0

    def is_on_finish(self):
        finish = arcade.get_sprites_in_rect(self.player.feet_hitbox, self.finish)
        return len(finish) > 0


class MyGame(arcade.View):
    def __init__(self, level_num, user_id):
        super().__init__()
        self.user_id = user_id

        self.tile_map = arcade.load_tilemap("test.tmx")
        self.scene = arcade.Scene.from_tilemap(self.tile_map)
        arcade.set_background_color(arcade.color.BLUE_SAPPHIRE)

        self.world_width = 80 * 64 # Ширина карты, кол-во тайлов * ширину тайла
        self.world_height = 20 * 64 # Высота карты

        self.coins_list = self.scene["coins"]
        self.finish_list = self.scene["finish"]

        self.coin_catching_sound = arcade.load_sound("assets/sounds/Звук начисления очков или бонусных баллов.mp3")
        self.jump_sound = arcade.load_sound("assets/sounds/video-game-vintage-jump-ascend_zkbs6f4_.mp3")
        self.start_climbing_sound = arcade.load_sound("assets/sounds/tree-branch-leaves-shaking_gy3csseu (mp3cut.net).mp3")
        self.bullet_miss_sound = arcade.load_sound("assets/sounds/Звук столкновения 8 бит.mp3")
        self.win_sound = arcade.load_sound("assets/sounds/4cccc379d8da21a.mp3")
        self.game_over_sound = arcade.load_sound("assets/sounds/45f8599eec7166a.mp3")
        self.player_hitted_sound = arcade.load_sound("assets/sounds/240d857e1b1a958.mp3")

        self.walls = self.scene["collisions"]
        self.platforms = arcade.SpriteList()

        plat = arcade.Sprite("assets/platform.png")
        plat.left = 200
        plat.bottom = 252
        plat.boundary_top = 600
        plat.boundary_bottom = 252
        plat.change_y = 2
        self.platforms.append(plat)

        self.ladders_top = self.scene["ladder_top"]
        self.last_top = []
        self.move_down = False

        self.world_camera = arcade.camera.Camera2D()
        self.last_y = 0
        self.gui_camera = arcade.camera.Camera2D()

    def setup(self):
        self.player = Player(self.user_id)
        self.player_list = arcade.SpriteList()
        self.player_list.append(self.player)

        self.player_is_jump = False
        self.jump_buffer_time = 0
        self.time_since_grounded = 1000.0
        self.last_y = -1

        self.bullets_list = arcade.SpriteList()
        self.enemies_list = arcade.SpriteList()
        self.damage_numbers_list = arcade.SpriteList()

        self.settings = arcade.SpriteList()
        setting = arcade.Sprite("assets/settings_icon.png", 1.0, self.width - 32, self.height - 32)
        self.settings.append(setting)

        self.pressed_keys = set() # Для хранения нажатых кнопок
        arcade.schedule(self.spawn_enemies, 4)

        self.engine = arcade.PhysicsEnginePlatformer(player_sprite=self.player, gravity_constant=GRAVITY, walls=self.walls, platforms=self.platforms)
        self.better_engine = BetterPhysicEngine(self.player, self.walls, self.platforms, self.ladders_top, self.scene["ladders"], self.finish_list)

        self.batch = Batch()
        self.coins_count = 0
        self.text_score = arcade.Text("Монеты: 0", 250, self.height - 20, arcade.color.WHITE, 24, anchor_x="left", anchor_y="top", batch=self.batch)
        self.health_text = arcade.Text(f"Здоровье: {self.player.health}", 20, self.height - 20,
                                       arcade.color.WHITE, 24, anchor_x="left", anchor_y="top", batch=self.batch)

    def on_draw(self) -> EVENT_HANDLE_STATE:
        self.clear()

        self.world_camera.use()

        self.scene.draw()
        self.player_list.draw()
        self.bullets_list.draw()
        self.enemies_list.draw()
        self.platforms.draw()
        self.damage_numbers_list.draw()

        self.gui_camera.use()

        self.settings.draw()
        self.batch.draw()

    def on_update(self, delta_time: float) -> bool | None:
        self.player.update(delta_time, self.pressed_keys)

        for bullet in self.bullets_list:
            # Передвигаем пулю
            bullet.update()
            # Проверяем на попадание в монстра
            killed_enemies = arcade.check_for_collision_with_list(bullet, self.enemies_list)
            for enemy in killed_enemies:
                cur_damage = randint(self.player.damage[0], self.player.damage[1])
                enemy.process_bullet_hit(cur_damage)

                if enemy.health <= 0:
                    # Начисляем две монеты за убийство врага
                    self.coins_count += 2
                    self.text_score.text = f"Монеты: {self.coins_count}"
                    cur_damage = 3 # Если враг убит - ставим другой знак

                number = DamageNumber(enemy.center_x + enemy.width / 2, enemy.center_y + enemy.height / 2, cur_damage)
                self.damage_numbers_list.append(number)

                # Удаляем и пулю, и врага
                bullet.remove_from_sprite_lists()

            walls_for_bullet = self.walls
            missed_bullets = arcade.check_for_collision_with_list(bullet, walls_for_bullet)
            if missed_bullets:
                arcade.stop_sound(self.player.player_sound)
                self.bullet_miss_sound.play()
                bullet.remove_from_sprite_lists()

        enemies = arcade.check_for_collision_with_list(self.player, self.enemies_list)
        for enemy in enemies:
            if enemy.can_attack:
                self.player.health -= 1
                enemy.reload()
                self.player_hitted_sound.play()

                self.health_text.text = f'Здоровье: {self.player.health}'
                if self.player.health > 0:
                    self.player.process_hit()
                else:
                    self.game_over_sound.play()

                    menu = MenuView()
                    self.window.show_view(menu)

        finish = self.better_engine.is_on_finish()
        if finish:
            con = sqlite3.connect("player.db")
            cursor = con.cursor()
            cursor.execute("UPDATE players SET money = ?", (self.coins_count, ))
            con.commit()

            self.win_sound.play()

            menu = MenuView()
            self.window.show_view(menu)


        catched_coins = arcade.check_for_collision_with_list(self.player, self.coins_list)
        for coin in catched_coins:
            self.coin_catching_sound.play()
            self.coins_count += 1
            self.text_score.text = f"Монеты: {self.coins_count}"
            coin.remove_from_sprite_lists()

        for enemy in self.enemies_list:
            enemy.update(delta_time, self.player.center_x)

        for number in self.damage_numbers_list:
            number.update(delta_time)

        # Если спрайт верхушки лестницы существует (то есть находится в списке стен)
        if len(self.last_top) > 0:
            # Если игрок находится СНИЗУ верхушки - удаляем её из списка стен
            if self.player.bottom < self.last_top[0].bottom:
                # В цикле, так как может быть 1 или 2 тайла
                while self.walls[-1] in self.ladders_top:
                    self.walls.pop()
                self.last_top.clear() # В конце очищаем список

        on_ladders = False
        top = self.better_engine.is_on_ladder_top()
        if top:
            # Если мы попали на верхушку лестницы (дошли до конца),
            # То считаем этот спрайт, как за стену
            self.last_top = top # Сохраняем в переменную, чтобы потом удалить из списка стен
            if self.move_down:
                # Если игрок на верхушке хочет спуститься вниз -
                # удаляем спрайт верхушки из списка стен
                self.player.change_y = -4
                while self.walls[-1] in self.ladders_top:
                    self.walls.pop()
                self.last_top.clear() # В конце очищаем список

            else:
                for i in range(len(top)):
                    if top[i] not in self.walls:
                        self.walls.append(top[i])
        else:
            on_ladders = self.better_engine.is_on_ladder()
            if on_ladders:
                if self.player_is_jump:
                    # Карабкаемся вверх
                    self.player.change_y = 4
                else:
                    # Если ничего не делаем - игрок медленно спускается вниз
                    self.player.change_y = -2

                if self.move_down:
                    # Если игрок хочет спуститься - ускоряем его спуск
                    self.player.change_y = -4

        camera_position = (self.player.center_x, self.player.center_y)
        grounded = self.engine.can_jump(y_distance=6) and self.better_engine.can_jump()
        if grounded:
            self.time_since_grounded = 0
            # Меняем текстуру на нормальную после приземления
            if self.player.is_jump:
                self.player.is_jump = False
                self.player.change_jump_texture()
            if self.player.is_climbing:
                self.player.is_climbing = False
                self.player.change_jump_texture()
        else:
            # Если игрок не на земле - он либо падает, либо поднимается по лестнице
            # Если игрок падает - не меняем положение камеры по y
            if not on_ladders:
                camera_position = (self.player.center_x, self.last_y)
            else:
                # Если попали на лестницу в прыжке или другим способом
                if not self.player.is_climbing:
                    self.player.is_climbing = True
                    self.player.texture = arcade.load_texture("assets/player/climbing.png")
                    self.start_climbing_sound.play()
            self.time_since_grounded += delta_time

        if self.jump_buffer_time > 0:
            self.jump_buffer_time -= delta_time

        want_jump = self.player_is_jump or (self.jump_buffer_time > 0)
        if want_jump:
            can_coyote = (self.time_since_grounded <= COYOTE_TIME)
            if grounded or can_coyote and not on_ladders:
                # во время прыжка оставляем камеру в неподвижном положении
                camera_position = (self.player.center_x, self.last_y)
                self.engine.jump(JUMP_SPEED)

                if not on_ladders:
                    # Если прыжок - меняем текстуру и звук на действие прыжка
                    self.player.is_jump = True
                    self.jump_sound.play()
                    self.player.change_jump_texture()
                else:
                    # Если забираемся по лестнице - меняем текстуру и звук на действие карабканья
                    self.player.is_climbing = True
                    self.player.texture = arcade.load_texture("assets/player/climbing.png")
                    self.start_climbing_sound.play()

                self.jump_buffer_time = 0
                # сбрасываем время с момента нахождения на земле
                # чтобы кайот-тайм не вызывался несколько раз
                self.time_since_grounded = 1000.0

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
            self.jump_buffer_time = JUMP_BUFFER
        elif symbol == arcade.key.S:
            self.move_down = True

        self.pressed_keys.add(symbol)

    def on_key_release(self, symbol: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if symbol == arcade.key.W:
            self.player_is_jump = False
            if self.player.change_y > 0:
                self.player.change_y *= 0.45
        elif symbol == arcade.key.S:
            self.move_down = False

        self.pressed_keys.remove(symbol)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> EVENT_HANDLE_STATE:
        if button == arcade.MOUSE_BUTTON_LEFT:
            # Если пользователь кликнул ЛКМ - герой атакует
            is_on_setting = arcade.get_sprites_at_point((x, y), self.settings)
            if is_on_setting:
                pause = PauseView(self)
                self.window.show_view(pause)
            else:
                self.player.attack(self.create_bullet)

    def create_bullet(self, center_x: float, center_y: float, direction: int):
        bullet = Bullet(center_x, center_y, direction)
        self.bullets_list.append(bullet)

    def spawn_enemies(self, delta_time):
        enemy = Enemy()
        self.enemies_list.append(enemy)


class MenuView(arcade.View):
    def __init__(self):
        super().__init__()
        self.user_id = 0
        self.load_user()

        self.background_color = arcade.color.BLUE_GRAY  # Фон для меню

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=True, space_between=10, height=200)

        self.setup_widgets()

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def load_user(self):
        if os.path.exists("local_user_id.txt"):
            with open("local_user_id.txt") as f:
                self.user_id = int(f.readline().strip())
        else:
            con = sqlite3.connect("player.db")
            cursor = con.cursor()
            cursor.execute("INSERT INTO players (health_level, damage_level, reload_level, money) VALUES (?, ?, ?, ?)",
                           (0, 0, 0, 0))
            con.commit()

            user_id = cursor.lastrowid
            with open("local_user_id.txt", "w") as f:
                f.write(str(user_id))

    def setup_widgets(self):
        play_texture = arcade.load_texture("assets/buttons/play.png")
        hovered_play_texture = arcade.load_texture("assets/buttons/hovered_play.png")
        pressed_play_texture = arcade.load_texture("assets/buttons/pressed_play.png")
        button_play = UITextureButton(texture=play_texture, texture_hovered=hovered_play_texture, texture_pressed=pressed_play_texture)
        button_play.on_click = self.start_game
        self.box_layout.add(button_play)

        shop_texture = arcade.load_texture("assets/buttons/shop.png")
        hovered_shop_texture = arcade.load_texture("assets/buttons/hovered_shop.png")
        pressed_shop_texture = arcade.load_texture("assets/buttons/pressed_shop.png")
        button_shop = UITextureButton(texture=shop_texture, texture_hovered=hovered_shop_texture, texture_pressed=pressed_shop_texture)
        button_shop.on_click = self.open_shop
        self.box_layout.add(button_shop)

        levels_texture = arcade.load_texture("assets/buttons/levels.png")
        hovered_level_texture = arcade.load_texture("assets/buttons/hovered_level.png")
        pressed_level_texture = arcade.load_texture("assets/buttons/pressed_level.png")
        button_levels = UITextureButton(texture=levels_texture, texture_hovered=hovered_level_texture, texture_pressed=pressed_level_texture)
        button_levels.on_click = self.show_levels
        self.box_layout.add(button_levels)

    def on_draw(self):
        self.clear()
        self.manager.draw()

    def start_game(self, event):
        game_view = MyGame(1, self.user_id)
        game_view.setup()
        self.manager.disable()
        self.window.show_view(game_view)

    def show_levels(self, event):
        levels_view = LevelsView(self.user_id)
        self.manager.disable()
        self.window.show_view(levels_view)

    def open_shop(self, event):
        shop_view = ShopView(self.user_id)
        self.manager.disable()
        self.window.show_view(shop_view)


class PauseView(arcade.View):
    def __init__(self, game_view):
        super().__init__()
        arcade.set_background_color(arcade.color.DARK_GRAY)
        self.game_view = game_view  # Сохраняем, чтобы вернуться

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout(y=100)
        self.box_layout = UIBoxLayout(vertical=True, space_between=120, height=100)
        self.buttons_layout = UIBoxLayout(vertical=True, space_between=10, height=200)

        self.setup_widgets()

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        pause_texture = arcade.load_texture("assets/pause_text.png")
        pause_image = UIImage(texture=pause_texture)
        self.box_layout.add(pause_image)

        continue_texture = arcade.load_texture("assets/buttons/continue.png")
        hovered_continue_texture = arcade.load_texture("assets/buttons/hovered_continue.png")
        pressed_continue_texture = arcade.load_texture("assets/buttons/pressed_continue.png")
        button_continue = UITextureButton(texture=continue_texture, texture_hovered=hovered_continue_texture,
                                          texture_pressed=pressed_continue_texture)
        button_continue.on_click = self.return_to_game
        self.buttons_layout.add(button_continue)

        exit_texture = arcade.load_texture("assets/buttons/exit.png")
        hovered_exit_texture = arcade.load_texture("assets/buttons/hovered_exit.png")
        pressed_exit_texture = arcade.load_texture("assets/buttons/pressed_exit.png")
        button_exit = UITextureButton(texture=exit_texture, texture_hovered=hovered_exit_texture,
                                      texture_pressed=pressed_exit_texture)
        button_exit.on_click = self.go_to_menu
        self.buttons_layout.add(button_exit)

        self.box_layout.add(self.buttons_layout)

    def on_draw(self):
        self.clear()
        self.manager.draw()

    def return_to_game(self, event):
        self.game_view.background_color = arcade.color.BLUE_SAPPHIRE
        self.manager.disable()
        self.window.show_view(self.game_view)

    def go_to_menu(self, event):
        message_box = UIMessageBox(
            width=300, height=200,
            message_text="Уверен, что хочешь выйти?\nПридется начинать сначала",
            buttons=("Да", "Нет")
        )
        message_box.on_action = self.on_message_button
        self.manager.add(message_box)

    def on_message_button(self, button_text):
        if button_text.action == "Да":
            menu = MenuView()
            self.manager.disable()
            self.window.show_view(menu)

class LevelsView(arcade.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        arcade.set_background_color(arcade.color.ANTIQUE_WHITE)

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=False)

        self.setup_widgets()
        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        back_texture = arcade.load_texture("assets/back_button.png")
        back_button = UITextureButton(texture=back_texture, x=15, y=515)
        back_button.on_click = self.back_to_menu
        self.manager.add(back_button)

        for i in range(1, 4):
            level_texture = arcade.load_texture(f"assets/levels_buttons/level_{i}.png")
            btn = UITextureButton(texture=level_texture)
            btn.on_click = lambda event, level=i: self.start_selected_level(level)
            self.box_layout.add(btn)

    def back_to_menu(self, event):
        menu = MenuView()
        self.manager.disable()
        self.window.show_view(menu)

    def on_draw(self) -> bool | None:
        self.clear()
        self.manager.draw()

    def start_selected_level(self, level_num):
        game = MyGame(level_num, self.user_id)
        game.setup()
        self.manager.disable()
        self.window.show_view(game)


class ShopView(arcade.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.items = ["health", "damage", "reload"]
        self.translate = ["здоровье", "урон", "перезарядку"]

        arcade.set_background_color(arcade.color.ANTIQUE_WHITE)

        self.manager = UIManager()
        self.manager.enable()

        self.anchor_layout = UIAnchorLayout()
        self.box_layout = UIBoxLayout(vertical=False)

        self.setup_widgets()

        con = sqlite3.connect("player.db")
        cursor = con.cursor()
        self.money_count = cursor.execute("SELECT money FROM players WHERE id = ?", (user_id, )).fetchone()[0]
        self.batch = Batch()
        self.money_text = arcade.Text(f"Монеты: {str(self.money_count)}", 590, 560, font_size=28,
                                      color=arcade.color.DARK_GRAY, anchor_x="left", batch=self.batch)

        self.anchor_layout.add(self.box_layout)
        self.manager.add(self.anchor_layout)

    def setup_widgets(self):
        back_texture = arcade.load_texture("assets/back_button.png")
        back_button = UITextureButton(texture=back_texture, x=15, y=515)
        back_button.on_click = self.back_to_menu
        self.manager.add(back_button)

        for i in range(1, 4):
            con = sqlite3.connect("player.db")
            cursor = con.cursor()
            request = f"SELECT {self.items[i - 1]}_level FROM players WHERE id = ?"
            level = cursor.execute(request, (self.user_id, )).fetchone()[0]

            box = UIBoxLayout(vertical=True, height=150, space_between=1)
            item_texture = arcade.load_texture(f"assets/shop/item_{i}.png")
            btn = UITextureButton(texture=item_texture)
            btn.on_click = lambda event, item=(i, level): self.buy_item(item)
            box.add(btn)


            item_level_row = UIBoxLayout(vertical=False, space_between=10)
            for i in range(level):
                level_texture = arcade.load_texture("assets/shop/bought_item.png")
                img = UIImage(texture=level_texture)
                item_level_row.add(img)

            for i in range(3 - level):
                level_texture = arcade.load_texture("assets/shop/non_bought_item.png")
                img = UIImage(texture=level_texture)
                item_level_row.add(img)

            box.add(item_level_row)
            self.box_layout.add(box)

    def on_draw(self) -> bool | None:
        self.clear()
        self.manager.draw()
        self.batch.draw()

    def back_to_menu(self, event):
        menu = MenuView()
        self.manager.disable()
        self.window.show_view(menu)

    def buy_item(self, selected_item: tuple[int, int]):
        # Если уже максимальный уровень - пропускаем
        if selected_item[1] == 3:
            return

        message_box = UIMessageBox(
            width=300, height=200,
            message_text=f"Уверен, что хочешь улучшить {self.translate[selected_item[0] - 1]}?",
            buttons=("Да", "Нет")
        )
        message_box.on_action = lambda event: self.on_message_button(event, selected_item)
        self.manager.add(message_box)

    def on_message_button(self, button_text, selected_item):
        prices = [15, 30, 45] # цена за 1, 2, 3 уровни
        if button_text.action == "Да":
            # Если хватает монет, чтобы купить
            if self.money_count >= prices[selected_item[1]]:
                con = sqlite3.connect("player.db")
                cursor = con.cursor()

                # Меняем кол-во монет
                self.money_count -= prices[selected_item[1]]
                self.money_text.text = f"Монеты: {str(self.money_count)}"

                # Обновляем монеты и уровень в бд
                request = f"UPDATE players SET money = ?, {self.items[selected_item[0] - 1]}_level = ?"
                cursor.execute(request, (self.money_count, selected_item[1] + 1))
                con.commit()

                # Не забываем отобразить изменения на экране
                self.box_layout.clear()
                self.setup_widgets()

            else:
                # Показываем игроку, что у него нет денег
                message_box = UIMessageBox(
                    width=300, height=200, message_text="Недостаточно монет!",
                    buttons=["OK"]
                )
                # Если нажал - ничего не делаем
                message_box.on_action = lambda event: 1
                self.manager.add(message_box)


def main():
    window = arcade.Window(800, 600, "Учимся ставить на паузу")
    menu_view = MenuView()
    window.show_view(menu_view)
    arcade.run()


if __name__ == "__main__":
    main()
