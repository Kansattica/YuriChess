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

def setup_pos(command, state):
	if "position" != command[0]:
		print_info("Weird, this command should start with 'position'. Instead, it's {}.".format(command))

	curr_idx = 1

	if "startpos" == command[curr_idx]:
		curr_idx += 1
		state.current_board = chess.Board()
	elif "fen" == command[curr_idx]:
		state.current_board.set_board_fen(command[curr_idx + 1])
		curr_idx += 2

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

def compute_weight(weight: int, weight_name: str, should_apply: bool, should_maximize_yuri: bool, max_weight: int, do_debug: bool):
	
	applied_weight = weight if should_maximize_yuri else (max_weight - weight)

	if should_apply:
		print_info("Multiplying in a weight of {} (original weight {}, {} inverted based on max_yuri) because I detected {}.".format(applied_weight, weight, "not" if should_maximize_yuri else max_weight,  weight_name))

	return max(1, applied_weight * should_apply)

def calculate_move_weight(move_name: str, state: YuriChessState):
	weight = 1

	move = chess.Move.from_uci(move_name)

	max_weight = state.max_weights()

	# Note that a weight of 1 is neutral and a weight of zero has to be max'd up to one so it doesn't make all the weights zero
	weight *= compute_weight(state.check_weight, "check", state.current_board.gives_check(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.en_passant_weight, "en passant", state.current_board.is_en_passant(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.capture_weight, "a capture", state.current_board.is_capture(move), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.promotion_weight, "a promotion", move.promotion != None, state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.queens_kissing_weight, "love winning", queens_kissing(state.current_board, move), state.maximize_yuri, max_weight, state.do_debug)

	state.current_board.push(move)

	# weigh novel moves (that don't lead to repeated board states) more heavily
	weight *= compute_weight(state.novel_move_weight, "a novel move", (not state.current_board.is_repetition(2)), state.maximize_yuri, max_weight, state.do_debug)
	weight *= compute_weight(state.checkmate_weight, "checkmate", state.current_board.is_checkmate(), state.maximize_yuri, max_weight, state.do_debug)

	state.current_board.pop()

	print_info("move {} has tiebreaker weight {}".format(move_name, weight))

	return weight


def resolve_tiebreaker(selected_best_move, selected_backup_best_move, yuri_moves, eval_func, backup_eval_func, state):
	tied_for_best = list(
		chain.from_iterable(
			# if a move is a repetition, make it less likely to be picked
			map(lambda x: repeat(x, calculate_move_weight(x["NameUCI"], state)),
			chain(
				filter(lambda x: eval_func(x) == eval_func(selected_best_move), yuri_moves),
				filter(lambda x: backup_eval_func(x) == backup_eval_func(selected_backup_best_move), yuri_moves)
		))))

	if len(tied_for_best) < 2:
		print_info("No tiebreaker to be done here.")
		return selected_best_move
	print_info("Resolving tiebreaker between {} weighted moves: {}".format(len(tied_for_best), " ".join(map(lambda x: x["Name"], tied_for_best))))

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
	return tied_for_best[int(eval_func(selected_best_move) * backup_eval_func(selected_backup_best_move) * backup_eval_func(calculate_yuri(repr(state.current_board)))) % len(tied_for_best)]

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
			print_info("New weights: Novel: {} Check: {} Checkmate: {} Capture: {} En Passant: {} Promotion: {} Queens Kissing: {}".format(state.novel_move_weight, state.check_weight, state.checkmate_weight, state.capture_weight, state.en_passant_weight, state.promotion_weight, state.queens_kissing_weight))
		
		

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
	   "option name QueensKissingWeight type spin default 2\n"
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