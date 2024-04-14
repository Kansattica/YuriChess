import sys
from itertools import chain, repeat, chain
import chess

from yuri_db import calculate_yuri, HASH_NUDGED_PREFIX, REVERSE_HASH_NUDGED_PREFIX
from yuri_state import YuriChessState

def print_info(str):
	print("info string " + str)

def init_board(_, state):
	#print_info("Resetting the board")
	#state.current_board = chess.Board()
	print("readyok")

def debug(command, state):
	state.do_debug = ("on" in command)

def index_or_negative_one(haystack: list[any], needle: any):
	try:
		return haystack.index(needle)
	except ValueError:
		return -1

def setup_pos(command, state):
	if "position" != command[0]:
		print_info("Weird, this command should start with 'position'. Instead, it's {}.".format(command))

	curr_idx = 1

	move_idx = index_or_negative_one(command, "moves")

	if "startpos" == command[curr_idx]:
		curr_idx += 1
		state.current_board = chess.Board()
	elif "fen" == command[curr_idx]:
		# fen command looks like:
  		# position fen rnbqkbnr/ppp1pppp/8/8/3q4/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1 moves f2f3
		# note the multiple spaces- we should look for where "moves" is and go based on that
		# or to the end of the array if there's no moves afterward
		# also, don't include the string "fen"
		curr_idx += 1
		state.current_board.set_fen(" ".join(command[curr_idx:move_idx]))
		curr_idx = move_idx

	if "moves" in command:
		if "moves" != command[curr_idx]:
			print_info("Weird, expected 'moves' at position {}.".format(curr_idx))
		curr_idx += 1

		for move in command[curr_idx:]:
			state.current_board.push_uci(move)

def print_best_move(_, state):
	print("bestmove " + state.last_best_move["NameUCI"])

def best_move(legal_moves, evaluation_func, min_or_max):
	return min_or_max(legal_moves, key=evaluation_func)

# If this move would put a queen next to another queen, then love wins
def queens_kissing(board: chess.Board, move: chess.Move):
	if board.piece_type_at(move.from_square) != chess.QUEEN:
		return False

	for queen_square in chain(board.pieces(chess.QUEEN, chess.WHITE), board.pieces(chess.QUEEN, chess.BLACK)):
		if queen_square != move.from_square and chess.square_distance(move.to_square, queen_square) == 1:
			return True
		
	return False

def horse_appreciation(board: chess.Board, move: chess.Move):
	for knight_square in board.pieces(chess.KNIGHT, board.turn):
		if chess.square_distance(move.to_square, knight_square) == 1:
			return True
		
	return False

def compute_weight(weight: int, weight_name: str, should_apply: bool, should_maximize_yuri: bool, max_weight: int, do_debug: bool):
	
	applied_weight = weight if should_maximize_yuri else (max_weight - weight)

	if should_apply:
		print_info("Multiplying in a weight of {} (original weight {}, {} inverted based on max_yuri) because I detected {}.".format(applied_weight, weight, "not" if should_maximize_yuri else max_weight,  weight_name))

	return max(1, applied_weight * should_apply)

def attack_other_color(board: chess.Board, square: chess.Square):
	for attacked_square in board.attacks(square):
		if board.color_at(attacked_square) == board.turn:
			return True
	return False


def calculate_move_weight(move_name: str, state: YuriChessState):
	weight = 1

	move = chess.Move.from_uci(move_name)

	max_weight = state.total_weights()

	# Note that a weight of 1 is neutral and a weight of zero has to be max'd up to one so it doesn't make all the weights zero
	weight *= compute_weight(state.check_weight, "check", state.current_board.gives_check(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.en_passant_weight, "en passant", state.current_board.is_en_passant(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.capture_weight, "a capture", state.current_board.is_capture(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.promotion_weight, "a promotion", move.promotion != None, state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.queens_kissing_weight, "love winning", queens_kissing(state.current_board, move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.castling_weight, "castling", state.current_board.is_castling(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.safety_weight, "safety. I hate when girls die", state.current_board.is_attacked_by(not state.current_board.turn, move.from_square) and not state.current_board.is_attacked_by(not state.current_board.turn, move.to_square) , state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.woman_respecting_weight, "an opportunity to respect women", not (state.current_board.is_capture(move) and state.current_board.piece_at(move.to_square).piece_type == chess.QUEEN), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.woman_disrespecting_weight, "an opportunity to disrespect women", state.current_board.is_capture(move) and state.current_board.piece_at(move.to_square).piece_type == chess.QUEEN, state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.horse_appreciation_weight , "an opportunity to appreciate a horse", horse_appreciation(state.current_board, move), state.maximize_yuri, max_weight, state.do_debug)

	state.current_board.push(move)

	# weigh novel moves (that don't lead to repeated board states) more heavily
	weight *= compute_weight(state.novel_move_weight, "a novel move", (not state.current_board.is_repetition(2)), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.checkmate_weight, "checkmate", state.current_board.is_checkmate(), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.attack_weight, "a chance to attack next turn", attack_other_color(state.current_board, move.to_square), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.attacked_weight, "being attacked", state.current_board.is_attacked_by(state.current_board.turn, move.to_square) != chess.BB_EMPTY, state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.pin_weight, "pinning (kabedon?)", state.current_board.pin(state.current_board.turn, move.to_square) != chess.BB_ALL, state.maximize_yuri, max_weight, state.do_debug)

	state.current_board.pop()

	print_info("move {} has tiebreaker weight {}".format(move_name, weight))

	return weight


def resolve_tiebreaker(selected_best_move, selected_backup_best_move, yuri_moves, eval_func, backup_eval_func, state):
	tied_for_best = list(
			map(lambda x: (x, calculate_move_weight(x["NameUCI"], state)),
			chain(
				filter(lambda x: eval_func(x) == eval_func(selected_best_move), yuri_moves),
				filter(lambda x: backup_eval_func(x) == backup_eval_func(selected_backup_best_move), yuri_moves)
		)))
	

	# since we always include selected_backup_best_move, this will probably never actually be used
	# there's a slight optimization here where if the moves are all the same, we just return that, but it'll happen regardless.
	# that'd be more worth if our evaluations were actually expensive to compute
	if len(tied_for_best) < 2:
		print_info("No tiebreaker to be done here.")
		return selected_best_move

	sum_weights = sum(map(lambda x: x[1], tied_for_best))

	print_info("Resolving tiebreaker between {} weighted moves, total weight {}: {}".format(len(tied_for_best), sum_weights, " ".join(map(lambda x: "{} ({})".format(x[0]["Name"], x[1]), tied_for_best))))

	# so the backup tiebreaker works, but it tends to lead to loops because it likes to pick the same two moves over and over
	# I think the modulo method is better because it's more sensitive to board states (a slight change in legal moves or the exact move being played tends to completely change the output)
	# Since I already wrote the backup stuff, I've decided to use the backup eval function to help "seed" the modulo so it gets to be part of the outcome.
	# Is that not yuri?
	# We also mix in the moves the backup evaluation function likes the best to both hopefully break out of loops and add some variety.

	#new_best_move = best_move(tied_for_best, backup_eval_func)
	#tied_for_tiebreaker_best = list(filter(lambda x: backup_eval_func(x) == backup_eval_func(new_best_move), yuri_moves))
	#if len(tied_for_tiebreaker_best) < 2:
	#	print_info("Tiebreaker worked!")
	#	return new_best_move

	#print_info("Resolving double tiebreaker between {} moves: {}".format(len(tied_for_tiebreaker_best)," ".join(map(lambda x: x["Name"], tied_for_tiebreaker_best)) ))

	# Because yuri exists in the world (and because I think it's useful for the tiebreaker to be sensitive to changes in board state to prevent loops), mix in the board state
	# use the hashnudged version of the board state because I suspect the regular version will fall into the lowercase letter pit a lot.
	# also scale by the combination of the weights we use to make sure that the tiebreaker and weights have at least kind of the same magnitude.
	yuri_tiebreaker = (int(eval_func(selected_best_move) * backup_eval_func(selected_backup_best_move) * backup_eval_func(calculate_yuri(repr(state.current_board)))) * state.total_weights()) % sum_weights

	weight_so_far = 0
	for possible_move, this_move_weight in tied_for_best:
		# each weight bucket is half open because the whole scale goes from [0, sum_weights)- tiebreaker will never be sum_weights because of the modulo operation
		if yuri_tiebreaker >= weight_so_far and yuri_tiebreaker < (weight_so_far + this_move_weight):
			print_info("{} (weight {}) is the best move because the tiebreaker value {} is between the accumulated weight {} and this move's weight plus the accumulated weight {}.".format(possible_move["Name"], this_move_weight, yuri_tiebreaker, weight_so_far, weight_so_far + this_move_weight))
			return possible_move
		weight_so_far += this_move_weight

	print_info("Aww, beans. I shouldn't have fallen out of the tiebreaker.")
	return None

def move_would_draw(current_board, move_name):
	algebraic_name = current_board.lan(chess.Move.from_uci(move_name))
	current_board.push_uci(move_name)
	will_draw = current_board.can_claim_draw() or current_board.is_stalemate() or current_board.is_repetition() or current_board.is_fifty_moves()
	if will_draw:
		print_info("Move {} ({}) will {}draw because{}{}{}".format(move_name, algebraic_name, "" if will_draw else "not ", " repetition" if current_board.can_claim_threefold_repetition() else "", " fifty move rule" if current_board.can_claim_fifty_moves() else "", " stalemate" if current_board.is_stalemate() else ""))
	current_board.pop()
	return will_draw

def move_to_yuri(move, board):
	yuricalc = calculate_yuri(board.lan(move))
	yuricalc["NameUCI"] = move.uci()
	return yuricalc

def search_moves(command: list[str], state: YuriChessState):
	if "go" != command[0]:
		print_info("Weird, this command should start with 'go'. Instead, it's {}.".format(command))

	yuried_moves = list(filter(lambda x: move_would_draw(state.current_board, x["NameUCI"]) == False, map(lambda m: move_to_yuri(m, state.current_board), state.current_board.legal_moves)))

	if not yuried_moves:
		print_info("All moves would draw or something! Playing the gayest move regardless.")
		yuried_moves = list(map(lambda m: move_to_yuri(m, state.current_board), state.current_board.legal_moves))

	if "searchmoves" in command:
		yuried_moves = [x for x in yuried_moves if x["NameUCI"] in command]

	for move in yuried_moves:
		print("info currmove {0} score cp {1} nodes {2} depth 1 seldepth 2 hashfull 0".format(move["NameUCI"], int(state.current_eval_func(move) * 100), len(yuried_moves) * 2))
		#print("info currmove {0} score cp {1} nodes {2} depth 1 seldepth 2 hashfull 0".format(move["NameUCI"], int(state.backup_eval_func(move) * 100), len(yuried_moves) * 2))

	first_best_move = best_move(yuried_moves, state.current_eval_func, state.min_or_max())
	best_backup_move = best_move(yuried_moves, state.backup_eval_func, state.min_or_max())

	state.last_best_move = resolve_tiebreaker(first_best_move, best_backup_move, yuried_moves, state.current_eval_func, state.backup_eval_func, state)

	print_info("I think the best move is {} with {} points and {} backup points.".format(state.last_best_move["Name"], state.current_eval_func(state.last_best_move), state.backup_eval_func(state.last_best_move)))

	chosen_move = chess.Move.from_uci(state.last_best_move["NameUCI"])
	if (state.current_board.is_en_passant(chosen_move)):
		print_info("Holy hell.")
	
	if (queens_kissing(state.current_board, chosen_move)):
		print_info("Love wins!")

	# the documentation says "don't stop searching until you get the stop command", but that just makes interactive play with unlimited time hang forever
	#if "infinite" not in command:
	print_best_move(command, state)	

def parse_check(checkstr):
	if checkstr.casefold() == "false":
		return False
	return True

def set_option(command: list[str], state: YuriChessState):
	# command looks like:
	# setoption name <option_name> value <value>
	com = command[2]
	option_arg = command[4]

	# all the weights could have been a dictionary or something. future refactor maybe
	if com == "YuriAttribute":
		state.current_eval_func = lambda x: x[option_arg]
		state.backup_eval_func = lambda x: x[HASH_NUDGED_PREFIX + option_arg]
		state.bonus_backup_eval_func = lambda x: x[REVERSE_HASH_NUDGED_PREFIX + option_arg]
		print_info("Evaluating moves based on {}.".format(option_arg))
	if com == "MaximizeYuri":
		state.maximize_yuri = parse_check(option_arg)
		print_info("{} the appropriate yuri attribute.".format("Maximizing" if state.maximize_yuri else "Minimizing"))
	if com == "NovelMoveWeight":
		if state.yuri_weight:
			print_info("Not setting NovelMoveWeight because yuri_weight already set!")
			return
		state.novel_move_weight = int(option_arg)
		print_info("When breaking ties, novel moves are {} times more likely.".format(state.novel_move_weight))
	if com == "CheckWeight":
		if state.yuri_weight:
			print_info("Not setting CheckWeight because yuri_weight already set!")
			return
		state.check_weight = int(option_arg)
		print_info("When breaking ties, moves that put the opponent in check are {} times more likely.".format(state.check_weight))
	if com == "CheckmateWeight":
		if state.yuri_weight:
			print_info("Not setting CheckmateWeight because yuri_weight already set!")
			return
		state.checkmate_weight = int(option_arg)
		print_info("When breaking ties, moves that put the opponent in checkmate are {} times more likely.".format(state.checkmate_weight))
	if com == "CaptureWeight":
		if state.yuri_weight:
			print_info("Not setting CaptureWeight because yuri_weight already set!")
			return
		state.capture_weight = int(option_arg)
		print_info("When breaking ties, moves that capture an opponent's piece are {} times more likely.".format(state.capture_weight))
	if com == "EnPassantWeight":
		if state.yuri_weight:
			print_info("Not setting EnPassantWeight because yuri_weight already set!")
			return
		state.en_passant_weight = int(option_arg)
		print_info("When breaking ties, en passant moves are {} times more likely. Holy hell.".format(state.en_passant_weight))
	if com == "PromotionWeight":
		if state.yuri_weight:
			print_info("Not setting PromotionWeight because yuri_weight already set!")
			return
		state.promotion_weight = int(option_arg)
		print_info("When breaking ties, promotion moves are {} times more likely.".format(state.promotion_weight))
	if com == "QueensKissingWeight":
		if state.yuri_weight:
			print_info("Not setting QueensKissingWeight because yuri_weight already set!")
			return
		state.queens_kissing_weight = int(option_arg)
		print_info("When breaking ties, moves that put one queen next to another are {} times more likely.".format(state.queens_kissing_weight))
	if com == "CastlingWeight":
		if state.yuri_weight:
			print_info("Not setting CastlingWeight because yuri_weight already set!")
			return
		state.castling_weight = int(option_arg)
		print_info("When breaking ties, moves that castle are {} times more likely.".format(state.castling_weight))
	if com == "AttackWeight":
		if state.yuri_weight:
			print_info("Not setting AttackWeight because yuri_weight already set!")
			return
		state.attack_weight = int(option_arg)
		print_info("When breaking ties, moves that threaten another piece are {} times more likely.".format(state.attack_weight))
	if com == "AttackedWeight":
		if state.yuri_weight:
			print_info("Not setting AttackedWeight because yuri_weight already set!")
			return
		state.attacked_weight = int(option_arg)
		print_info("When breaking ties, moves that put our own pieces into danger are {} times more likely.".format(state.attacked_weight))
	if com == "SafetyWeight":
		if state.yuri_weight:
			print_info("Not setting SafetyWeight because yuri_weight already set!")
			return
		state.safety_weight = int(option_arg)
		print_info("When breaking ties, moves that take threatened pieces out of danger are {} times more likely.".format(state.safety_weight))
	if com == "PinWeight":
		if state.yuri_weight:
			print_info("Not setting PinWeight because yuri_weight already set!")
			return
		state.pin_weight = int(option_arg)
		print_info("When breaking ties, moves that pin the enemy king are {} times more likely.".format(state.pin_weight))
	if com == "WomanRespectingWeight":
		if state.yuri_weight:
			print_info("Not setting WomanRespectingWeight because yuri_weight already set!")
			return
		state.woman_respecting_weight = int(option_arg)
		print_info("When breaking ties, moves that don't capture an enemy queen are {} times more likely because we respect women.".format(state.woman_respecting_weight))
	if com == "WomanDisrespectingWeight":
		if state.yuri_weight:
			print_info("Not setting WomanDisrespectingWeight because yuri_weight already set!")
			return
		state.woman_disrespecting_weight = int(option_arg)
		print_info("When breaking ties, moves that capture an enemy queen are {} times more likely because we disrespect women.".format(state.woman_disrespecting_weight))
	if com == "HorseAppreciationWeight":
		if state.yuri_weight:
			print_info("Not setting HorseAppreciationWeight because yuri_weight already set!")
			return
		state.horse_appreciation_weight = int(option_arg)
		print_info("When breaking ties, moves that pet a friendly horse are {} times more likely.".format(state.horse_appreciation_weight))
	if com == "YuriWeight":
		state.yuri_weight = parse_check(option_arg)
		if state.yuri_weight:
			print_info("Doing yuri weighting. Asking the evaluation function what scores it applies to each weight. Hope you set YuriAttribute how you wanted!")
			state.novel_move_weight = int(state.current_eval_func(calculate_yuri("Novel")))
			state.check_weight = int(state.current_eval_func(calculate_yuri("Check")))
			state.checkmate_weight = int(state.current_eval_func(calculate_yuri("Checkmate")))
			state.capture_weight = int(state.current_eval_func(calculate_yuri("Capture")))
			state.en_passant_weight = int(state.current_eval_func(calculate_yuri("En Passant")))
			state.promotion_weight = int(state.current_eval_func(calculate_yuri("Promotion")))
			state.queens_kissing_weight = int(state.current_eval_func(calculate_yuri("Queens Kissing")))
			state.castling_weight = int(state.current_eval_func(calculate_yuri("Castling")))
			state.attack_weight = int(state.current_eval_func(calculate_yuri("Attack")))
			state.attacked_weight = int(state.current_eval_func(calculate_yuri("Attacked")))
			state.safety_weight = int(state.current_eval_func(calculate_yuri("Safety")))
			state.pin_weight = int(state.current_eval_func(calculate_yuri("Pin")))
			state.woman_respecting_weight = int(state.current_eval_func(calculate_yuri("Respecting Women")))
			state.woman_disrespecting_weight = int(state.current_eval_func(calculate_yuri("Disrespecting Women")))
			state.horse_appreciation_weight = int(state.current_eval_func(calculate_yuri("Horse Appreciation")))
			print_info("New weights: Novel: {} Check: {} Checkmate: {} Capture: {} En Passant: {} Promotion: {} Queens Kissing: {} Castling: {} Attack: {} Attacked: {} Safety: {} Pin: {} Woman Respecting: {} Woman Disrespecting: {} Horse Appreciation: {}".format(state.novel_move_weight, state.check_weight, state.checkmate_weight, state.capture_weight, state.en_passant_weight, state.promotion_weight, state.queens_kissing_weight, state.castling_weight, state.attack_weight, state.attacked_weight, state.safety_weight, state.pin_weight, state.woman_respecting_weight, state.woman_disrespecting_weight, state.horse_appreciation_weight))
		
		

def uci_intro(_, __):
	print("id name YuriFish\n"
	   "id author The Internet's Beloved Princess Grace\n"
	   "option name YuriAttribute type combo default Sum var Sum var Gayness var Boldness var Commitment var Lewdness\n"
	   "option name MaximizeYuri type check default true\n"
	   "option name YuriWeight type check default false\n"
	   "option name NovelMoveWeight type spin default 2\n"
	   "option name CheckWeight type spin default 1\n"
	   "option name CheckmateWeight type spin default 3\n"
	   "option name CaptureWeight type spin default 1\n"
	   "option name EnPassantWeight type spin default 2\n"
	   "option name PromotionWeight type spin default 2\n"
	   "option name QueensKissingWeight type spin default 5\n"
	   "option name CastlingWeight type spin default 2\n"
	   "option name AttackWeight type spin default 1\n"
	   "option name AttackedWeight type spin default 1\n"
	   "option name SafetyWeight type spin default 1\n"
	   "option name PinWeight type spin default 2\n"
	   "option name WomanRespectingWeight type spin default 5\n"
	   "option name WomanDisrespectingWeight type spin default 1\n"
	   "option name HorseAppreciationWeight type spin default 3\n"
	   "uciok"),

def no_op(_, __):
	pass

uci_commands = {
	"uci": uci_intro,
	"position": setup_pos,
	"isready": init_board,
	"ucinewgame": init_board,
	"debug": debug,
	"stop": print_best_move,
	"go": search_moves,
	"setoption": set_option,
	"register": no_op,
	"xboard": no_op,
	"": no_op
}

print_info("Welcome to YuriFish!")

state = YuriChessState()

for line in sys.stdin:
	command = line.strip()
	#print_info(command)
	if "quit" in command:
		break

	split_command = command.split()
	
	try:
		uci_commands[split_command[0]](split_command, state)
	except KeyError:
		print_info("Got command {} that I didn't know what to do with.".format(command))


	sys.stdout.flush()

print("Thanks for yuri!")